import logging
from typing import Dict, Any, Optional

from langchain_core.memory import BaseMemory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from pydantic import Field

from database import DatabaseManager
from models import Lead


class DatabaseMemory(BaseMemory):
    """Custom LangChain memory that stores conversation in PostgreSQL database"""

    # Define Pydantic fields properly
    db_manager: DatabaseManager = Field(exclude=True)  # Exclude from serialization
    lead_id: int
    memory_key: str = Field(default="history")
    window_size: int = Field(default=10)

    class Config:
        arbitrary_types_allowed = True  # Allow non-serializable types like DatabaseManager

    def __init__(self, db_manager: DatabaseManager, lead_id: int, memory_key: str = "history",
                 window_size: int = 10, **kwargs):
        # Initialize parent class first
        super().__init__(
            db_manager=db_manager,
            lead_id=lead_id,
            memory_key=memory_key,
            window_size=window_size,
            **kwargs
        )

    @property
    def memory_variables(self) -> list[str]:
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        messages = self.db_manager.get_conversation_history(self.lead_id, self.window_size)

        formatted_messages = []
        for msg in messages:
            if msg.sender == "user":
                formatted_messages.append(HumanMessage(content=msg.content))
            else:
                formatted_messages.append(AIMessage(content=msg.content))

        return {self.memory_key: formatted_messages}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        # Save user message
        if "input" in inputs:
            self.db_manager.save_message(self.lead_id, "user", inputs["input"])

        # Save bot response
        if "response" in outputs:
            self.db_manager.save_message(self.lead_id, "bot", outputs["response"])

    def clear(self) -> None:
        # In this implementation, we don't delete from DB, just reset memory
        pass


class CryptoSalesBot:
    def __init__(self,
                 openai_api_key: str,
                 database_url: str,
                 model_name: str = "gpt-4",  # Replace with your fine-tuned model
                 bot_id: str = "crypto_sales_bot_v1"):

        self.db_manager = DatabaseManager(database_url)
        self.bot_id = bot_id

        # Initialize LLM with your fine-tuned model
        self.llm = ChatOpenAI(
            api_key=openai_api_key,
            model=model_name,  # Use your fine-tuned model here
            temperature=0.7
        )

        # Sales prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.get_system_prompt()),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def get_system_prompt(self) -> str:
        return """IMPORTANT: You MUST ALWAYS respond in English only, regardless of what language the user writes in. Never respond in Polish, Spanish, French, or any other language - only English.

You are Alex, a friendly and knowledgeable crypto fintech sales representative. You understand all languages but you ALWAYS respond ONLY in English. Your goal is to:

        1. Build rapport with potential customers
        2. Understand their crypto/fintech needs and pain points
        3. Present our crypto fintech solutions (trading platforms, DeFi tools, crypto banking services)
        4. Guide conversations toward booking a discovery call with our team

        Key points about our services:
        - Advanced crypto trading platform with AI-powered insights
        - DeFi yield optimization tools
        - Crypto-backed lending and banking services
        - Enterprise blockchain solutions
        - 24/7 customer support

        Sales approach:
        - Be conversational and helpful, not pushy
        - Ask qualifying questions about their current crypto activities
        - Share relevant success stories and use cases
        - Address concerns about security and regulation
        - Create urgency around market opportunities
        - Always aim to book a meeting for deeper discussion

        Meeting booking phrases to use:
        - "Would you like to schedule a brief 15-minute call to discuss how this could work for your situation?"
        - "I'd love to show you a personalized demo - when would be a good time this week?"
        - "Let me connect you with our specialist team - are you available for a quick call?"

        Keep responses conversational, under 1 sentence unless explaining complex topics.
        If someone shows interest, immediately offer to book a meeting."""

    def get_or_create_lead(self, telegram_chat_id: str, name: str = None, username: str = None) -> Lead:
        return self.db_manager.get_or_create_lead(
            bot_id=self.bot_id,
            telegram_chat_id=telegram_chat_id,
            name=name,
            username=username
        )

    async def process_message(self, telegram_chat_id: str, user_message: str,
                              user_name: str = None, username: str = None) -> str:
        """Process incoming message and return bot response"""

        # Get or create lead
        lead = self.get_or_create_lead(telegram_chat_id, user_name, username)

        # Initialize memory for this conversation
        memory = DatabaseMemory(
            db_manager=self.db_manager,
            lead_id=lead.id,
            memory_key="history",
            window_size=10
        )

        try:
            # Load conversation history
            memory_vars = memory.load_memory_variables({})

            # Generate response
            response = await self.chain.ainvoke({
                "input": user_message,
                "history": memory_vars["history"]
            })

            bot_response = response.content

            # Check if user is interested in booking a meeting
            if self.is_meeting_request(user_message):
                meeting_link = self.generate_meeting_link(lead.id)
                bot_response += f"\n\nHere's your booking link: {meeting_link}"

            # Save conversation to database
            memory.save_context(
                {"input": user_message},
                {"response": bot_response}
            )

            return bot_response

        except Exception as e:
            logging.error(f"Error processing message: {e}")
            return "I apologize, but I'm having some technical difficulties. Please try again in a moment."

    def is_meeting_request(self, message: str) -> bool:
        """Check if user is interested in booking a meeting"""
        meeting_keywords = [
            "book", "schedule", "meeting", "call", "demo", "talk", "discuss",
            "yes", "interested", "sure", "sounds good", "when", "available",
            "tomorrow", "today", "next week", "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday", "morning", "afternoon",
            "evening", "time", "free", "can we", "let's", "ok", "okay", "fine"
        ]
        return any(keyword in message.lower() for keyword in meeting_keywords)

    def generate_meeting_link(self, lead_id: int) -> str:
        """Generate meeting booking link (integrate with your calendar system)"""
        # Replace with your actual calendar booking system (Calendly, etc.)
        return f"https://calendly.com/your-company/crypto-consultation?lead_id={lead_id}"


def create_bot(config: dict) -> CryptoSalesBot:
    """Factory function to create configured bot"""
    return CryptoSalesBot(
        openai_api_key=config["OPENAI_API_KEY"],
        database_url=config["DATABASE_URL"],
        model_name=config.get("MODEL_NAME", "gpt-4"),  # Your fine-tuned model
        bot_id=config.get("BOT_ID", "crypto_sales_bot_v1")
    )


# Alternative approach using composition instead of inheritance
class SimpleDatabaseMemory:
    """Alternative memory implementation using composition instead of inheritance"""

    def __init__(self, db_manager: DatabaseManager, lead_id: int, memory_key: str = "history", window_size: int = 10):
        self.db_manager = db_manager
        self.lead_id = lead_id
        self.memory_key = memory_key
        self.window_size = window_size

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        messages = self.db_manager.get_conversation_history(self.lead_id, self.window_size)

        formatted_messages = []
        for msg in messages:
            if msg.sender == "user":
                formatted_messages.append(HumanMessage(content=msg.content))
            else:
                formatted_messages.append(AIMessage(content=msg.content))

        return {self.memory_key: formatted_messages}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        # Save user message
        if "input" in inputs:
            self.db_manager.save_message(self.lead_id, "user", inputs["input"])

        # Save bot response
        if "response" in outputs:
            self.db_manager.save_message(self.lead_id, "bot", outputs["response"])


# Version using the simple memory approach
class CryptoSalesBotSimple:
    def __init__(self,
                 openai_api_key: str,
                 database_url: str,
                 model_name: str = "gpt-4",
                 bot_id: str = "crypto_sales_bot_v1"):

        self.db_manager = DatabaseManager(database_url)
        self.bot_id = bot_id

        self.llm = ChatOpenAI(
            api_key=openai_api_key,
            model=model_name,
            temperature=0.7
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.get_system_prompt()),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def get_system_prompt(self) -> str:
        return """You are Alex, a friendly and knowledgeable crypto fintech sales representative. Your goal is to:

        1. Build rapport with potential customers
        2. Understand their crypto/fintech needs and pain points
        3. Present our crypto fintech solutions (trading platforms, DeFi tools, crypto banking services)
        4. Guide conversations toward booking a discovery call with our team

        Key points about our services:
        - Advanced crypto trading platform with AI-powered insights
        - DeFi yield optimization tools
        - Crypto-backed lending and banking services
        - Enterprise blockchain solutions
        - 24/7 customer support

        Sales approach:
        - Be conversational and helpful, not pushy
        - Ask qualifying questions about their current crypto activities
        - Share relevant success stories and use cases
        - Address concerns about security and regulation
        - Create urgency around market opportunities
        - Always aim to book a meeting for deeper discussion

        Meeting booking phrases to use:
        - "Would you like to schedule a brief 15-minute call to discuss how this could work for your situation?"
        - "I'd love to show you a personalized demo - when would be a good time this week?"
        - "Let me connect you with our specialist team - are you available for a quick call?"

        Keep responses conversational, under 2-3 sentences unless explaining complex topics.
        If someone shows interest, immediately offer to book a meeting."""

    def get_or_create_lead(self, telegram_chat_id: str, name: str = None, username: str = None) -> Lead:
        return self.db_manager.get_or_create_lead(
            bot_id=self.bot_id,
            telegram_chat_id=telegram_chat_id,
            name=name,
            username=username
        )

    async def process_message(self, telegram_chat_id: str, user_message: str,
                              user_name: str = None, username: str = None) -> str:
        """Process incoming message and return bot response"""

        # Get or create lead
        lead = self.get_or_create_lead(telegram_chat_id, user_name, username)

        # Initialize simple memory
        memory = SimpleDatabaseMemory(self.db_manager, lead.id)

        try:
            # Load conversation history
            memory_vars = memory.load_memory_variables({})

            # Generate response
            response = await self.chain.ainvoke({
                "input": user_message,
                "history": memory_vars["history"]
            })

            bot_response = response.content

            # Save conversation to database
            memory.save_context(
                {"input": user_message},
                {"response": bot_response}
            )

            return bot_response

        except Exception as e:
            logging.error(f"Error processing message: {e}")
            return "I apologize, but I'm having some technical difficulties. Please try again in a moment."

    def generate_meeting_link(self, lead_id: int) -> str:
        """Generate meeting booking link (integrate with your calendar system)"""
        return f"https://calendly.com/your-company/crypto-consultation?lead_id={lead_id}"