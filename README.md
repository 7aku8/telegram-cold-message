# 🤖 Telegram Crypto Lead Generation Bot

A sophisticated Telegram bot that monitors cryptocurrency-related groups and automatically identifies potential business leads using AI analysis. The bot intelligently filters messages to find users discussing crypto projects or companies that might benefit from business banking services.

## ✨ Features

- 🔍 **AI-Powered Lead Detection** - Uses OpenAI GPT to analyze messages and identify relevant business opportunities
- 📊 **Multi-Group Monitoring** - Simultaneously monitors multiple Telegram groups
- 🎯 **Smart Targeting** - Only messages users who appear to be working on crypto-related projects
- ⏰ **Rate Limiting** - Built-in cooldown system to prevent spam and respect Telegram's limits
- 🗄️ **Persistent Storage** - SQLite database tracks contacted users to avoid duplicate messages
- 🔔 **Webhook Integration** - Optional n8n webhook notifications for lead tracking
- 🛡️ **Security First** - Runs as isolated system user with restricted permissions
- 📝 **Comprehensive Logging** - Full audit trail with automatic log rotation

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│  Telegram API   │───▶│   Your Bot   │───▶│   OpenAI API    │
│   (Groups)      │    │              │    │  (AI Analysis)  │
└─────────────────┘    └──────┬───────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │   SQLite DB  │
                       │ (User Tracking)│
                       └──────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Linux server with systemd
- Root/sudo access
- Telegram API credentials
- OpenAI API key

### Installation

1. **Clone or download the project files**
   ```bash
   # You'll need these files:
   bot.py                    # Main bot script
   .env                      # Environment configuration
   telegram-bot.service      # Systemd service file
   install-telegram-bot.sh   # Installation script
   ```

2. **Configure your environment**
   Create a `.env` file with your credentials:
   ```bash
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   OPENAI_API_KEY=your_openai_api_key
   WEBHOOK_URL=https://your-n8n-webhook.com/webhook  # Optional
   ```

3. **Make the installer executable**
   ```bash
   chmod +x install-telegram-bot.sh
   ```

4. **Run the installation**
   ```bash
   sudo ./install-telegram-bot.sh
   ```

That's it! 🎉 The bot will automatically start and begin monitoring configured groups.

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_ID` | ✅ | Telegram API ID from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | ✅ | Telegram API Hash from [my.telegram.org](https://my.telegram.org) |
| `OPENAI_API_KEY` | ✅ | OpenAI API key for message analysis |
| `WEBHOOK_URL` | ❌ | Optional webhook for lead notifications |

### Bot Configuration

Edit the `bot.py` file to customize:

```python
# Target chat IDs (get these from Telegram)
chat_ids = [
    1626522644,  # Gubbin's lounge
    1652712042,  # Suits Calls | USA
    # Add more group IDs here
]

# Rate limiting (minutes between messages)
COOLDOWN_MINUTES = 15

# Custom message template
message_template = '''Your custom outreach message here...'''
```

### Getting Telegram Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Go to "API Development Tools"
4. Create a new application
5. Copy your `API_ID` and `API_HASH`

### Finding Group Chat IDs

Use this Python snippet to find group IDs:

```python
from telethon import TelegramClient

async def get_chat_ids():
    async for dialog in client.iter_dialogs():
        if dialog.is_group:
            print(f"{dialog.name}: {dialog.id}")

# Run this to list all your groups and their IDs
```

## 🛠️ Service Management

### Check Service Status
```bash
sudo systemctl status telegram-bot
```

### View Live Logs
```bash
sudo journalctl -u telegram-bot -f
```

### Control the Service
```bash
# Start the bot
sudo systemctl start telegram-bot

# Stop the bot
sudo systemctl stop telegram-bot

# Restart the bot
sudo systemctl restart telegram-bot

# Enable auto-start on boot
sudo systemctl enable telegram-bot

# Disable auto-start
sudo systemctl disable telegram-bot
```

## 📁 File Structure

After installation, your bot files will be organized as:

```
/opt/telegram-bot/
├── bot.py                 # Main bot script
├── .env                   # Environment variables
├── venv/                  # Python virtual environment
├── messaged_users.db      # SQLite database
├── sent_messages_log.txt  # Message log
└── requirements.txt       # Python dependencies

/etc/systemd/system/
└── telegram-bot.service   # Service configuration

/var/log/telegram-bot/
└── *.log                  # Application logs (with rotation)
```

## 🔧 Troubleshooting

### Common Issues

**Bot not starting:**
```bash
# Check for errors in logs
sudo journalctl -u telegram-bot --no-pager

# Test Python dependencies
sudo -u telegram-bot /opt/telegram-bot/venv/bin/python -c "import telethon, openai"
```

**Permission errors:**
```bash
# Fix file permissions
sudo chown -R telegram-bot:telegram-bot /opt/telegram-bot
sudo chmod 600 /opt/telegram-bot/.env
```

**Database issues:**
```bash
# Check database permissions
sudo ls -la /opt/telegram-bot/messaged_users.db

# Reset database (if needed)
sudo rm /opt/telegram-bot/messaged_users.db
sudo systemctl restart telegram-bot
```

### Log Locations

- **Service logs:** `sudo journalctl -u telegram-bot`
- **Application logs:** `/var/log/telegram-bot/`
- **Message history:** `/opt/telegram-bot/sent_messages_log.txt`

## 🔒 Security Features

- **Isolated user:** Bot runs as dedicated `telegram-bot` user
- **Restricted permissions:** Limited file system access
- **Secure storage:** Environment variables protected with 600 permissions
- **Process isolation:** systemd security hardening enabled
- **Log rotation:** Automatic cleanup of old log files

## 📊 Monitoring & Analytics

### Built-in Tracking

The bot automatically tracks:
- Messages sent and recipients
- Rate limiting status
- AI analysis results
- Error conditions

### Optional Webhook Integration

Configure a webhook URL to receive notifications when leads are identified:

```json
{
  "username": "crypto_entrepreneur",
  "timestamp": "2025-06-03T10:30:00"
}
```

Perfect for integration with tools like n8n, Zapier, or custom dashboards.

## 🤝 Contributing

Found a bug or want to add a feature? Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## ⚠️ Important Notes

- **Respect Telegram's Terms:** Ensure your use complies with Telegram's Terms of Service
- **Rate Limiting:** The bot includes built-in rate limiting to prevent abuse
- **Privacy:** Be mindful of user privacy and data protection regulations
- **Testing:** Always test in a controlled environment before production use

## 📄 License

This project is provided as-is for educational and legitimate business purposes. Please use responsibly and in compliance with all applicable laws and platform terms of service.

---

**Made with ❤️ for the crypto business community**

Need help? Check the logs first, then create an issue with detailed error informatio