import asyncio
import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class PendingMessage:
    content: str
    timestamp: datetime
    sender_name: str
    username: str


class MessageDebouncer:
    """Handles message debouncing to respond once to multiple rapid messages"""

    def __init__(self, debounce_seconds: float = 3.0):
        self.debounce_seconds = debounce_seconds
        self.pending_messages: Dict[str, List[PendingMessage]] = defaultdict(list)
        self.timers: Dict[str, asyncio.Task] = {}
        self.bot = None
        self.client = None

    def set_bot_and_client(self, bot, client):
        """Set bot and client references"""
        self.bot = bot
        self.client = client

    async def add_message(self, chat_id: str, message: str, sender_name: str, username: str):
        """Add a message and handle debouncing"""

        # Cancel existing timer for this chat if it exists
        if chat_id in self.timers:
            self.timers[chat_id].cancel()

        # Add message to pending list
        pending_msg = PendingMessage(
            content=message,
            timestamp=datetime.datetime.now(),
            sender_name=sender_name,
            username=username
        )
        self.pending_messages[chat_id].append(pending_msg)

        print(
            f"📝 Added message from {sender_name} (chat: {chat_id}). Total pending: {len(self.pending_messages[chat_id])}")

        # Start new timer
        self.timers[chat_id] = asyncio.create_task(
            self._process_after_delay(chat_id)
        )

    async def _process_after_delay(self, chat_id: str):
        """Wait for debounce period then process all pending messages"""
        try:
            await asyncio.sleep(self.debounce_seconds)
            await self._process_pending_messages(chat_id)
        except asyncio.CancelledError:
            print(f"⏰ Timer cancelled for chat {chat_id} (new message received)")
        except Exception as e:
            print(f"❌ Error in debounce timer for chat {chat_id}: {e}")

    async def _process_pending_messages(self, chat_id: str):
        """Process all pending messages for a chat"""
        if chat_id not in self.pending_messages or not self.pending_messages[chat_id]:
            return

        messages = self.pending_messages[chat_id].copy()
        self.pending_messages[chat_id].clear()

        if chat_id in self.timers:
            del self.timers[chat_id]

        print(f"🔄 Processing {len(messages)} pending messages for chat {chat_id}")

        # Combine all messages into one input
        if len(messages) == 1:
            combined_message = messages[0].content
        else:
            # Format multiple messages
            message_parts = []
            for i, msg in enumerate(messages, 1):
                timestamp_str = msg.timestamp.strftime("%H:%M:%S")
                message_parts.append(f"[{timestamp_str}] {msg.content}")

            combined_message = f"User sent {len(messages)} messages:\n" + "\n".join(message_parts)

        # Use the latest message's sender info
        latest_msg = messages[-1]

        try:
            # Process combined message
            response = await self.bot.process_message(
                telegram_chat_id=chat_id,
                user_message=combined_message,
                user_name=latest_msg.sender_name,
                username=latest_msg.username
            )

            print(f"✅ Sending combined response to chat {chat_id}: {response[:100]}...")
            await self.client.send_message(int(chat_id), response)

        except Exception as e:
            print(f"❌ Error processing combined messages for chat {chat_id}: {e}")
            # Send error message
            await self.client.send_message(
                int(chat_id),
                "I apologize, but I'm having some technical difficulties. Please try again in a moment."
            )