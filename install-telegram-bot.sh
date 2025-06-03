#!/bin/bash

# Telegram Bot Installation Script
# This script sets up the Telegram bot as a systemd service

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="telegram-bot"
SERVICE_USER="telegram-bot"
SERVICE_GROUP="telegram-bot"
INSTALL_DIR="/opt/telegram-bot"
PYTHON_SCRIPT="bot.py"
SERVICE_FILE="telegram-bot.service"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if required files exist
check_files() {
    local required_files=("$PYTHON_SCRIPT" ".env" "$SERVICE_FILE")
    local missing_files=()

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            missing_files+=("$file")
        fi
    done

    if [[ ${#missing_files[@]} -gt 0 ]]; then
        print_error "Missing required files:"
        for file in "${missing_files[@]}"; do
            echo "  - $file"
        done
        print_error "Please ensure all files are in the current directory:"
        echo "  - $PYTHON_SCRIPT (your Python bot script)"
        echo "  - .env (environment variables file)"
        echo "  - $SERVICE_FILE (systemd service file)"
        exit 1
    fi
}

# Install system dependencies
install_dependencies() {
    print_status "Installing system dependencies..."

    # Detect package manager and install dependencies
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv sqlite3
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip python3-venv sqlite3
    elif command -v dnf &> /dev/null; then
        dnf install -y python3 python3-pip python3-venv sqlite3
    elif command -v pacman &> /dev/null; then
        pacman -Sy --noconfirm python python-pip python-virtualenv sqlite
    else
        print_error "Unsupported package manager. Please install Python 3, pip, venv, and sqlite3 manually."
        exit 1
    fi

    print_success "System dependencies installed"
}

# Create service user and group
create_user() {
    print_status "Creating service user and group..."

    if ! getent group "$SERVICE_GROUP" &> /dev/null; then
        groupadd --system "$SERVICE_GROUP"
        print_success "Created group: $SERVICE_GROUP"
    else
        print_warning "Group $SERVICE_GROUP already exists"
    fi

    if ! getent passwd "$SERVICE_USER" &> /dev/null; then
        useradd --system --gid "$SERVICE_GROUP" --home-dir "$INSTALL_DIR" \
                --shell /bin/false --comment "Telegram Bot Service" "$SERVICE_USER"
        print_success "Created user: $SERVICE_USER"
    else
        print_warning "User $SERVICE_USER already exists"
    fi
}

# Create installation directory
create_directory() {
    print_status "Creating installation directory..."

    mkdir -p "$INSTALL_DIR"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    chmod 755 "$INSTALL_DIR"

    print_success "Created directory: $INSTALL_DIR"
}

# Set up Python virtual environment
setup_venv() {
    print_status "Setting up Python virtual environment..."

    # Create virtual environment
    sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"

    # Upgrade pip
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip

    print_success "Virtual environment created"
}

# Install Python dependencies
install_python_deps() {
    print_status "Installing Python dependencies..."

    # Create requirements.txt if it doesn't exist
    if [[ ! -f "requirements.txt" ]]; then
        print_status "Creating requirements.txt..."
        cat > requirements.txt << EOF
telethon>=1.32.0
openai>=1.0.0
aiohttp>=3.8.0
python-dotenv>=1.0.0
certifi>=2023.0.0
EOF
    fi

    # Install requirements
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt

    print_success "Python dependencies installed"
}

# Copy application files
copy_files() {
    print_status "Copying application files..."

    # Copy Python script
    cp "$PYTHON_SCRIPT" "$INSTALL_DIR/"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/$PYTHON_SCRIPT"
    chmod 644 "$INSTALL_DIR/$PYTHON_SCRIPT"

    # Copy .env file
    cp ".env" "$INSTALL_DIR/"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"  # Restrict access to sensitive file

    # Copy requirements.txt if exists
    if [[ -f "requirements.txt" ]]; then
        cp "requirements.txt" "$INSTALL_DIR/"
        chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/requirements.txt"
        chmod 644 "$INSTALL_DIR/requirements.txt"
    fi

    print_success "Application files copied"
}

# Install systemd service
install_service() {
    print_status "Installing systemd service..."

    # Copy service file
    cp "$SERVICE_FILE" "/etc/systemd/system/"
    chmod 644 "/etc/systemd/system/$SERVICE_FILE"

    # Reload systemd
    systemctl daemon-reload

    # Enable service
    systemctl enable "$SERVICE_NAME"

    print_success "Systemd service installed and enabled"
}

# Create log directory
create_logs() {
    print_status "Setting up logging..."

    # Create log directory
    mkdir -p "/var/log/$SERVICE_NAME"
    chown "$SERVICE_USER:$SERVICE_GROUP" "/var/log/$SERVICE_NAME"
    chmod 755 "/var/log/$SERVICE_NAME"

    # Create logrotate configuration
    cat > "/etc/logrotate.d/$SERVICE_NAME" << EOF
/var/log/$SERVICE_NAME/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_GROUP
}
EOF

    print_success "Logging configured"
}

# Test configuration
test_config() {
    print_status "Testing configuration..."

    # Check if .env file has required variables
    if ! grep -q "API_ID" "$INSTALL_DIR/.env" || \
       ! grep -q "API_HASH" "$INSTALL_DIR/.env" || \
       ! grep -q "OPENAI_API_KEY" "$INSTALL_DIR/.env"; then
        print_warning "Please ensure your .env file contains all required variables:"
        echo "  - API_ID"
        echo "  - API_HASH"
        echo "  - OPENAI_API_KEY"
        echo "  - WEBHOOK_URL (optional)"
    fi

    # Test Python import
    if sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/python" -c "import telethon, openai, aiohttp, dotenv" 2>/dev/null; then
        print_success "Python dependencies test passed"
    else
        print_error "Python dependencies test failed"
        exit 1
    fi
}

# Start service
start_service() {
    print_status "Starting $SERVICE_NAME service..."

    systemctl start "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service started successfully"
    else
        print_error "Service failed to start. Check logs with: journalctl -u $SERVICE_NAME -f"
        exit 1
    fi
}

# Main installation function
main() {
    echo "========================================="
    echo "   Telegram Bot Installation Script"
    echo "========================================="
    echo

    check_root
    check_files

    print_status "Starting installation..."

    install_dependencies
    create_user
    create_directory
    setup_venv
    install_python_deps
    copy_files
    create_logs
    install_service
    test_config
    start_service

    echo
    echo "========================================="
    print_success "Installation completed successfully!"
    echo "========================================="
    echo
    echo "Service status: $(systemctl is-active $SERVICE_NAME)"
    echo "Service logs:   journalctl -u $SERVICE_NAME -f"
    echo "Start service:  systemctl start $SERVICE_NAME"
    echo "Stop service:   systemctl stop $SERVICE_NAME"
    echo "Restart:        systemctl restart $SERVICE_NAME"
    echo "Status:         systemctl status $SERVICE_NAME"
    echo
    echo "Application directory: $INSTALL_DIR"
    echo "Log directory: /var/log/$SERVICE_NAME"
    echo
    print_warning "Remember to check your .env file configuration!"
}

# Run main function
main "$@"