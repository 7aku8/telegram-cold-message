import logging
from typing import Dict, Any

from langchain_core.memory import BaseMemory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_openai_functions_agent, AgentExecutor
from pydantic import Field

from database import DatabaseManager
from models import Lead


class DatabaseMemory(BaseMemory):
    """Custom LangChain memory that stores conversation in PostgreSQL database"""

    # Define Pydantic fields properly
    db_manager: DatabaseManager = Field(exclude=True)  # Exclude from serialization
    lead_id: int
    memory_key: str = Field(default="history")
    window_size: int = Field(default=20)

    class Config:
        arbitrary_types_allowed = True  # Allow non-serializable types like DatabaseManager

    def __init__(self, db_manager: DatabaseManager, lead_id: int, memory_key: str = "history",
                 window_size: int = 20, **kwargs):
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


# Version using the simple memory approach with tools
class CryptoSalesBot:
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

        # Create tools
        self.tools = self._create_tools()

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.get_system_prompt()),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # Create agent with tools
        self.agent = create_openai_functions_agent(self.llm, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)

    def _create_tools(self):
        """Create LangChain tools for the bot"""

        @tool
        def generate_booking_link(lead_id: int) -> str:
            """Generate a meeting booking link for a lead. Use this when users want to schedule a meeting or call."""
            return f"https://calendly.com/your-company/crypto-consultation?lead_id={lead_id}"

        return [generate_booking_link]

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

        TOOLS AVAILABLE:
        - generate_booking_link: Use this tool when users express interest in booking a meeting, call, or demo. The tool requires a lead_id parameter.

        When users show interest in scheduling (words like "yes", "sure", "tomorrow", "call", "meeting", "talk", "schedule"), immediately use the generate_booking_link tool to provide them with a booking link."""

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
        memory = DatabaseMemory(self.db_manager, lead.id)

        try:
            # Load conversation history
            memory_vars = memory.load_memory_variables({})

            # Prepare input for agent executor
            agent_input = {
                "input": user_message,
                "chat_history": memory_vars["history"]
            }

            # Generate response using agent (with tools)
            response = await self.agent_executor.ainvoke(agent_input)
            bot_response = response['output']

            # Save conversation to database
            memory.save_context(
                {"input": user_message},
                {"response": bot_response}
            )

            return bot_response

        except Exception as e:
            logging.error(f"Error processing message: {e}")
            return "I apologize, but I'm having some technical difficulties. Please try again in a moment."


def create_bot(config: dict) -> CryptoSalesBot:
    """Factory function to create configured bot"""
    return CryptoSalesBot(
        openai_api_key=config["OPENAI_API_KEY"],
        database_url=config["DATABASE_URL"],
        model_name=config.get("MODEL_NAME", "gpt-4"),  # Your fine-tuned model
        bot_id=config.get("BOT_ID", "crypto_sales_bot_v1")
    )