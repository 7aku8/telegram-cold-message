import asyncio
import os
import random

from telethon import TelegramClient, events
import openai
from dotenv import load_dotenv

from utils.conversation import create_bot
from utils.database import get_lead, create_lead, create_message
from utils.ai_utils import is_lead_relevant, generate_first_message
from utils.message_debouncer import MessageDebouncer
from utils.only_leads import run_only_for_leads
from utils.webhook import send_webhook
from utils.working_hours import run_only_in_working_hours

load_dotenv()

# === CONFIGURATION ===
api_id = int(os.getenv("API_ID", 1))
api_hash = os.getenv("API_HASH", "your_api_hash_here")
session_name = 'sessions/bot'

chat_ids = [
    -4876574630,  # P100 - Crypto Business Accounts
]

openai.api_key = os.getenv("OPENAI_API_KEY", "your_openai_api_key_here")
webhook_url = os.getenv("WEBHOOK_URL", "https://your-n8n-webhook-url.com/webhook")

message_template = '''Hi, I saw you're active in some crypto-related groups. If you're running a project or company in the crypto space, you might find what we do at P100 interesting, we offer crypto-friendly business accounts, 
IBANs, wallets, and Mastercards, all accessible via API.

Let me know if that sounds relevant, happy to share more details.
'''

client = TelegramClient(session_name, api_id, api_hash)

# === RATE LIMITING ===
COOLDOWN_MINUTES = 15

# === DEBOUNCING ===
DEBOUNCE_SECONDS = 5.0  # Wait 3 seconds after last message before responding
message_debouncer = MessageDebouncer(debounce_seconds=DEBOUNCE_SECONDS)


def can_process_messages():
    """Check if enough time has passed since last message to process new ones"""
    return True


def get_remaining_cooldown_minutes():
    """Get remaining minutes in cooldown period"""
    return 0


bot = create_bot({
    "OPENAI_API_KEY": openai.api_key,
    "DATABASE_URL": os.getenv("DATABASE_URL", "sqlite:///./database.db"),
    "BOT_ID": os.getenv("BOT_ID", "unknown"),
    "MODEL_NAME": os.getenv("FINE_TUNED_MODEL", "gpt-4.1")
})

# Set bot and client references for debouncer
message_debouncer.set_bot_and_client(bot, client)


@run_only_in_working_hours
# @client.on(events.NewMessage())
@client.on(events.NewMessage(incoming=True))
@run_only_for_leads
async def on_new_message(event):
    """Handle incoming messages from existing leads with debouncing"""
    chat_id = str(event.chat_id)

    sender = await event.get_sender()
    sender_name = sender.first_name or "there"
    username = sender.username if sender.username else "no_username"

    print(f"📨 Received message from {sender_name} (chat: {chat_id})")

    # Add message to debouncer instead of processing immediately
    await message_debouncer.add_message(
        chat_id=chat_id,
        message=event.message.message,
        sender_name=sender_name,
        username=username
    )


# === MAIN EVENT HANDLER ===
@run_only_in_working_hours
@client.on(events.NewMessage(chat_ids))
async def handler(event):
    """Handle new messages from monitored groups"""
    sender = await event.get_sender()
    sender_name = sender.first_name or "there"
    sender_id = sender.id
    username = sender.username if sender.username else "no_username"
    text = event.message.message

    print(f"New message from {sender_name} (ID: {sender_id})")

    # Check if we're still in cooldown period
    if not can_process_messages():
        remaining_minutes = get_remaining_cooldown_minutes()
        print(f"⏳ Rate limit active. {remaining_minutes} minutes remaining before processing messages again.")
        return

    # Skip if already messaged
    if get_lead(sender_id):
        print(f"⚠️ Already messaged {sender_name} (ID: {sender_id}), skipping...")
        return

    if is_lead_relevant(text):
        try:
            print(f"✅ Relevant message detected from {sender_name} (ID: {sender_id})")

            if os.getenv("ENVIRONMENT") == "production":
                delay_minutes = random.randint(2, 6)
                delay_seconds = delay_minutes * 60
                print(f"⏳ Sleeping for {delay_minutes} minutes before messaging {sender_name}...")
                await asyncio.sleep(delay_seconds)

            message = generate_first_message(sender_name, text)

            await client.send_message(sender_id, message)

            print(f"🔒 Rate limit activated. No messages will be processed for {COOLDOWN_MINUTES} minutes.")

            lead = create_lead(sender_id, os.getenv("BOT_ID", "unknown"), sender_name, username)
            print(f"Lead created: {lead}")
            create_message(lead.id, 'bot', message)

            # Send webhook
            await send_webhook(username)
            print(f"📩 Message and webhook sent for {sender_name}")
        except Exception as e:
            print(f"❌ Failed to message {sender_name}: {e}")


# === CLEANUP ON SHUTDOWN ===
async def cleanup():
    """Clean up pending timers on shutdown"""
    print("🧹 Cleaning up pending message timers...")
    for chat_id, timer in message_debouncer.timers.items():
        if not timer.done():
            timer.cancel()
    print("✅ Cleanup completed")


async def get_pending_stats():
    """Get statistics about pending messages"""
    total_pending = sum(len(messages) for messages in message_debouncer.pending_messages.values())
    active_chats = len(message_debouncer.pending_messages)
    active_timers = len(message_debouncer.timers)

    print(f"📊 Pending Messages Stats:")
    print(f"   - Total pending messages: {total_pending}")
    print(f"   - Active chats with pending messages: {active_chats}")
    print(f"   - Active timers: {active_timers}")

    for chat_id, messages in message_debouncer.pending_messages.items():
        if messages:
            print(f"   - Chat {chat_id}: {len(messages)} pending messages")


# === ENHANCED SYSTEM PROMPT ===
# Update the system prompt in your conversation.py to handle multiple messages:
ENHANCED_SYSTEM_PROMPT_ADDITION = """
IMPORTANT: Users may send multiple messages in quick succession. When you receive an input that contains multiple timestamped messages like:

"User sent 3 messages:
[14:23:15] Hello
[14:23:18] Are you there?
[14:23:20] I'm interested in your services"

Respond to the complete context of all messages as one coherent conversation. Don't acknowledge that there were multiple messages unless relevant. Just respond naturally to the overall intent and content.
"""

if __name__ == "__main__":
    try:
        with client:
            print("🤖 Bot is running and monitoring the group...")
            print(f"⏰ Rate limiting: {COOLDOWN_MINUTES} minute cooldown after each message sent")
            print(f"🕒 Message debouncing: {DEBOUNCE_SECONDS} seconds wait after last message")
            print("\nDebouncing behavior:")
            print("  - Multiple rapid messages are collected")
            print(f"  - Bot waits {DEBOUNCE_SECONDS} seconds after the last message")
            print("  - Responds once to all collected messages")
            print("\nPress Ctrl+C to stop...")
            client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        asyncio.run(cleanup())
    except Exception as e:
        print(f"❌ Bot crashed: {e}")
        asyncio.run(cleanup())