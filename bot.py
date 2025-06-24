import asyncio
import os
import random
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import hashlib

from telethon import TelegramClient, events
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
import certifi
import ssl
import aiohttp

# LangChain imports
from langchain.memory import ConversationSummaryBufferMemory, VectorStoreRetrieverMemory
from langchain.schema import Document, BaseMessage, HumanMessage, AIMessage
from langchain.chains import ConversationChain
from langchain.prompts import PromptTemplate
from langchain_openai import OpenAI, ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent, AgentOutputParser
from langchain.prompts import StringPromptTemplate
from langchain.schema import AgentAction, AgentFinish
from langchain.memory.chat_memory import ChatMessageHistory
from typing import List, Union
import re

load_dotenv()

ssl_context = ssl.create_default_context(cafile=certifi.where())

# === CONFIGURATION ===
api_id = int(os.getenv("API_ID", 1))
api_hash = os.getenv("API_HASH", "your_api_hash_here")
session_name = 'filip_session'
BOT_INSTANCE_ID = os.getenv("BOT_INSTANCE_ID", "bot1")

# Groups for this bot instance
chat_ids = [
    1626522644,  # Gubbin's lounge
]

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'telegram_sales_bot'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

# ChromaDB configuration
CHROMA_PERSIST_DIR = os.getenv('CHROMA_PERSIST_DIR', './chroma_db')

# LangChain configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your_openai_api_key_here")
webhook_url = os.getenv("WEBHOOK_URL", "https://your-n8n-webhook-url.com/webhook")

# Rate limiting
COOLDOWN_MINUTES = 15
MESSAGE_DELAY_MIN = 2
MESSAGE_DELAY_MAX = 6

# Initialize Telegram client
client = TelegramClient(session_name, api_id, api_hash)

# === DATABASE SETUP ===
# Create connection pool for PostgreSQL
db_pool = SimpleConnectionPool(1, 20, **DB_CONFIG)


def get_db_connection():
    return db_pool.getconn()


def return_db_connection(conn):
    db_pool.putconn(conn)


def init_database():
    """Initialize PostgreSQL database schema"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Users table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    bot_instance VARCHAR(50)
                )
            ''')

            # Conversations table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    stage VARCHAR(50) DEFAULT 'initial',
                    qualified BOOLEAN DEFAULT FALSE,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    summary TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb
                )
            ''')

            # Messages table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    role VARCHAR(20),
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Rate limiting table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bot_instance VARCHAR(50) PRIMARY KEY,
                    last_message_time TIMESTAMP
                )
            ''')

            # Message locks for distributed processing
            cur.execute('''
                CREATE TABLE IF NOT EXISTS message_locks (
                    message_hash VARCHAR(64) PRIMARY KEY,
                    bot_instance VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Lead scoring table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS lead_scores (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                    score INTEGER DEFAULT 0,
                    factors JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create indexes
            cur.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_message_locks_created_at ON message_locks(created_at)')

            conn.commit()
    finally:
        return_db_connection(conn)


# === SALES CONVERSATION TEMPLATE ===
SALES_AGENT_TEMPLATE = """You are Filip, a conversational sales representative for P100, a company providing crypto-friendly business infrastructure.

Current conversation stage: {stage}
Customer name: {customer_name}
Conversation history summary: {history_summary}

Your personality:
- Friendly and conversational, not pushy
- Knowledgeable about crypto and fintech
- Solution-focused
- Ask qualifying questions naturally

Conversation stages:
1. Initial Contact: Introduce yourself and P100 briefly, gauge interest
2. Discovery: Understand their business, needs, and pain points
3. Solution Presentation: Show how P100 solves their specific problems
4. Objection Handling: Address concerns naturally
5. Closing: Suggest next steps (demo call, email details, etc.)

P100 key features:
- Business accounts with IBANs for international transfers
- Crypto wallets (BTC, ETH, USDT, etc.) integrated with fiat
- Mastercard cards for team spending
- Everything accessible via REST API
- No hidden fees, transparent pricing
- 24/7 support
- Compliance-first approach (KYB included)

Remember to:
- Keep responses short (2-3 sentences)
- Ask one question at a time
- Listen and respond to their specific situation
- Move the conversation forward naturally

Current message from {customer_name}: {input}

Your response:"""

# === LANGCHAIN SETUP ===
# Initialize ChromaDB for conversation memory
embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
vectorstore = Chroma(
    collection_name="conversations",
    embedding_function=embeddings,
    persist_directory=CHROMA_PERSIST_DIR
)

# Initialize LLM
llm = ChatOpenAI(
    openai_api_key=OPENAI_API_KEY,
    model_name="gpt-4",
    temperature=0.7
)


class SalesConversationChain:
    """Custom conversation chain for sales interactions"""

    def __init__(self, user_id: int, user_name: str):
        self.user_id = user_id
        self.user_name = user_name
        self.stage = self.get_conversation_stage()

        # Create custom memory with vector store for better context
        self.memory = ConversationSummaryBufferMemory(
            llm=llm,
            max_token_limit=500,
            return_messages=True
        )

        # Load previous conversation if exists
        self.load_conversation_history()

        # Create the conversation chain
        self.prompt = PromptTemplate(
            input_variables=["stage", "customer_name", "history_summary", "input"],
            template=SALES_AGENT_TEMPLATE
        )

        self.chain = ConversationChain(
            llm=llm,
            memory=self.memory,
            prompt=self.prompt,
            verbose=True
        )

    def get_conversation_stage(self) -> str:
        """Get current conversation stage from database"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT stage FROM conversations WHERE user_id = %s",
                    (self.user_id,)
                )
                result = cur.fetchone()
                return result['stage'] if result else 'initial'
        finally:
            return_db_connection(conn)

    def update_conversation_stage(self, new_stage: str):
        """Update conversation stage in database"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE conversations 
                    SET stage = %s, last_activity = CURRENT_TIMESTAMP 
                    WHERE user_id = %s
                    """,
                    (new_stage, self.user_id)
                )
                conn.commit()
                self.stage = new_stage
        finally:
            return_db_connection(conn)

    def load_conversation_history(self):
        """Load previous conversation from database"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT role, content 
                    FROM messages 
                    WHERE user_id = %s 
                    ORDER BY timestamp 
                    LIMIT 20
                    """,
                    (self.user_id,)
                )
                messages = cur.fetchall()

                for msg in messages:
                    if msg['role'] == 'user':
                        self.memory.chat_memory.add_user_message(msg['content'])
                    else:
                        self.memory.chat_memory.add_ai_message(msg['content'])
        finally:
            return_db_connection(conn)

    def save_message(self, role: str, content: str):
        """Save message to database and vector store"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s)",
                    (self.user_id, role, content)
                )
                conn.commit()

            # Also save to vector store for similarity search
            doc = Document(
                page_content=content,
                metadata={
                    "user_id": self.user_id,
                    "role": role,
                    "timestamp": datetime.now().isoformat()
                }
            )
            vectorstore.add_documents([doc])
        finally:
            return_db_connection(conn)

    def analyze_intent_and_update_stage(self, user_message: str, bot_response: str):
        """Analyze conversation to determine stage transitions"""
        # Simple rule-based stage progression (can be enhanced with LLM)
        user_lower = user_message.lower()

        if self.stage == 'initial':
            if any(word in user_lower for word in ['yes', 'interested', 'tell me', 'sure']):
                self.update_conversation_stage('discovery')
                self.update_lead_score(20, {"showed_interest": True})

        elif self.stage == 'discovery':
            if any(word in user_lower for word in ['need', 'problem', 'looking for', 'help with']):
                self.update_conversation_stage('solution_presentation')
                self.update_lead_score(30, {"expressed_need": True})

        elif self.stage == 'solution_presentation':
            if any(word in user_lower for word in ['how much', 'pricing', 'cost', 'expensive']):
                self.update_conversation_stage('objection_handling')
            elif any(word in user_lower for word in ['sounds good', 'interested', 'like it']):
                self.update_conversation_stage('closing')
                self.update_lead_score(40, {"positive_feedback": True})

        elif self.stage == 'objection_handling':
            if any(word in user_lower for word in ['ok', 'makes sense', 'understand']):
                self.update_conversation_stage('closing')

    def update_lead_score(self, points: int, factors: dict):
        """Update lead score based on conversation"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lead_scores (user_id, score, factors) 
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        score = lead_scores.score + %s,
                        factors = lead_scores.factors || %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (self.user_id, points, json.dumps(factors), points, json.dumps(factors))
                )
                conn.commit()
        finally:
            return_db_connection(conn)

    async def generate_response(self, user_message: str) -> str:
        """Generate response using LangChain"""
        # Save user message
        self.save_message('user', user_message)

        # Get conversation summary for context
        history_summary = self.memory.predict_new_summary(
            self.memory.chat_memory.messages,
            ""
        )

        # Generate response
        response = self.chain.predict(
            stage=self.stage,
            customer_name=self.user_name,
            history_summary=history_summary,
            input=user_message
        )

        # Save bot response
        self.save_message('assistant', response)

        # Analyze and update stage
        self.analyze_intent_and_update_stage(user_message, response)

        return response


# === BOT FUNCTIONS ===
class LeadQualifier:
    """Advanced lead qualification using LangChain"""

    def __init__(self):
        self.qualification_prompt = PromptTemplate(
            input_variables=["message"],
            template="""Analyze this message to determine if the sender is a potential B2B crypto/fintech lead.

Look for indicators like:
- Running or building a crypto/blockchain project
- Mentioning business needs (banking, payments, cards)
- Discussing company operations or scaling
- Seeking infrastructure or API solutions
- Team or company references

Message: {message}

Return a JSON response:
{{
    "is_lead": true/false,
    "confidence": 0.0-1.0,
    "indicators": ["indicator1", "indicator2"],
    "company_stage": "startup/growing/established/unknown"
}}"""
        )

        self.chain = LLMChain(llm=llm, prompt=self.qualification_prompt)

    def qualify_lead(self, message: str) -> Tuple[bool, float, dict]:
        """Qualify if message indicates a potential lead"""
        try:
            result = self.chain.run(message=message)
            data = json.loads(result)
            return data["is_lead"], data["confidence"], data
        except:
            # Fallback to simple keyword matching
            keywords = ['project', 'company', 'building', 'launching', 'startup',
                        'payment', 'banking', 'api', 'integration', 'scale']
            matches = sum(1 for keyword in keywords if keyword in message.lower())
            is_lead = matches >= 2
            confidence = min(matches * 0.3, 1.0)
            return is_lead, confidence, {"method": "fallback"}


# Initialize lead qualifier
lead_qualifier = LeadQualifier()


# === DATABASE HELPER FUNCTIONS ===
def create_or_update_user(user_id: int, username: str, first_name: str, last_name: str = None):
    """Create or update user in database"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, bot_instance)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
                """,
                (user_id, username, first_name, last_name, BOT_INSTANCE_ID)
            )

            # Create conversation record
            cur.execute(
                """
                INSERT INTO conversations (user_id)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                """,
                (user_id,)
            )
            conn.commit()
    finally:
        return_db_connection(conn)


def try_acquire_message_lock(message_text: str, sender_id: int) -> bool:
    """Try to acquire lock for processing a message"""
    message_hash = hashlib.md5(
        f"{sender_id}:{message_text[:100]}:{datetime.now().date()}".encode()
    ).hexdigest()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO message_locks (message_hash, bot_instance) VALUES (%s, %s)",
                    (message_hash, BOT_INSTANCE_ID)
                )
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                conn.rollback()
                return False
    finally:
        return_db_connection(conn)


def check_rate_limit() -> bool:
    """Check if we can send a message (rate limiting)"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT last_message_time FROM rate_limits WHERE bot_instance = %s",
                (BOT_INSTANCE_ID,)
            )
            result = cur.fetchone()

            if not result:
                return True

            last_time = result['last_message_time']
            time_diff = datetime.now() - last_time
            return time_diff.total_seconds() >= (COOLDOWN_MINUTES * 60)
    finally:
        return_db_connection(conn)


def update_rate_limit():
    """Update rate limit timestamp"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rate_limits (bot_instance, last_message_time)
                VALUES (%s, CURRENT_TIMESTAMP)
                ON CONFLICT (bot_instance)
                DO UPDATE SET last_message_time = CURRENT_TIMESTAMP
                """,
                (BOT_INSTANCE_ID,)
            )
            conn.commit()
    finally:
        return_db_connection(conn)


def has_already_messaged(user_id: int) -> bool:
    """Check if we've already messaged this user"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM messages WHERE user_id = %s)",
                (user_id,)
            )
            return cur.fetchone()[0]
    finally:
        return_db_connection(conn)


# === WEBHOOK FUNCTION ===
async def send_webhook(user_id: int, username: str, event_type: str, metadata: dict = None):
    """Send webhook notification"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get lead score
            cur.execute(
                "SELECT score, factors FROM lead_scores WHERE user_id = %s",
                (user_id,)
            )
            lead_data = cur.fetchone()

            payload = {
                'user_id': user_id,
                'username': username,
                'event_type': event_type,
                'timestamp': datetime.now().isoformat(),
                'bot_instance': BOT_INSTANCE_ID,
                'lead_score': lead_data['score'] if lead_data else 0,
                'metadata': metadata or {}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, ssl=ssl_context) as resp:
                    if resp.status == 200:
                        print(f"✅ Webhook sent: {event_type} for {username}")
                    else:
                        print(f"❌ Webhook failed: {resp.status}")
    except Exception as e:
        print(f"🚨 Webhook error: {e}")
    finally:
        return_db_connection(conn)


# === EVENT HANDLERS ===
@client.on(events.NewMessage(chats=chat_ids))
async def handle_group_message(event):
    """Handle messages in monitored groups"""
    sender = await event.get_sender()
    if not sender or sender.bot:
        return

    sender_id = sender.id
    sender_name = sender.first_name or "there"
    username = sender.username or f"user_{sender_id}"
    text = event.message.message

    # Try to acquire lock
    if not try_acquire_message_lock(text, sender_id):
        return

    print(f"📨 Analyzing message from {sender_name}: {text[:50]}...")

    # Check rate limit
    if not check_rate_limit():
        print(f"⏳ Rate limit active")
        return

    # Skip if already contacted
    if has_already_messaged(sender_id):
        return

    # Qualify lead using LangChain
    is_lead, confidence, metadata = lead_qualifier.qualify_lead(text)

    if is_lead and confidence >= 0.6:
        print(f"🎯 Qualified lead detected: {sender_name} (confidence: {confidence})")

        # Create user record
        create_or_update_user(sender_id, username, sender.first_name, sender.last_name)

        # Random delay
        delay = random.randint(MESSAGE_DELAY_MIN, MESSAGE_DELAY_MAX)
        print(f"⏳ Waiting {delay} minutes...")
        await asyncio.sleep(delay * 60)

        # Initialize conversation chain
        conversation = SalesConversationChain(sender_id, sender_name)

        # Generate personalized initial message
        initial_message = await conversation.generate_response(
            f"Context: User said '{text[:100]}...' in a crypto group. Start a conversation."
        )

        # Send message
        await client.send_message(sender_id, initial_message)
        update_rate_limit()

        # Send webhook
        await send_webhook(
            sender_id, username, "initial_contact",
            {"confidence": confidence, "qualification": metadata}
        )


@client.on(events.NewMessage(func=lambda e: e.is_private))
async def handle_private_message(event):
    """Handle private conversations"""
    sender = await event.get_sender()
    if not sender or sender.bot or sender.id == (await client.get_me()).id:
        return

    sender_id = sender.id
    sender_name = sender.first_name or "User"
    username = sender.username or f"user_{sender_id}"
    text = event.message.message

    print(f"💬 Private message from {sender_name}: {text[:50]}...")

    # Initialize or get conversation
    conversation = SalesConversationChain(sender_id, sender_name)

    # Show typing indicator
    async with client.action(sender_id, 'typing'):
        # Generate response
        response = await conversation.generate_response(text)

        # Natural typing delay
        await asyncio.sleep(random.uniform(2, 5))

        # Send response
        await client.send_message(sender_id, response)

    # Check if qualified
    if conversation.stage in ['solution_presentation', 'closing']:
        await send_webhook(
            sender_id, username, "lead_qualified",
            {"stage": conversation.stage}
        )


# === CLEANUP FUNCTIONS ===
async def cleanup_old_locks():
    """Clean up old message locks"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM message_locks WHERE created_at < %s",
                (datetime.now() - timedelta(days=1),)
            )
            conn.commit()
    finally:
        return_db_connection(conn)


# === MAIN ===
async def main():
    # Initialize database
    init_database()

    # Start client
    await client.start()
    print(f"🤖 Advanced LangChain Bot '{BOT_INSTANCE_ID}' is running...")
    print(f"📊 Monitoring {len(chat_ids)} groups")
    print(f"🧠 Using LangChain for intelligent conversations")
    print(f"💾 PostgreSQL + ChromaDB for distributed state")

    # Cleanup old locks
    await cleanup_old_locks()

    # Run
    await client.run_until_disconnected()


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())