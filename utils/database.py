import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlmodel import select, Session, SQLModel
from utils.models import Lead, Message

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.db")

engine = create_engine(DATABASE_URL, echo=True,
                       connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})


def get_lead(telegram_chat_id: str):
    with Session(engine) as session:
        statement = select(Lead).where(Lead.telegram_chat_id == str(telegram_chat_id))
        result = session.exec(statement)
        return result.one_or_none()


def create_lead(telegram_chat_id: str, bot_id: str, name: str = None, username: str = None):
    lead = Lead(telegram_chat_id=telegram_chat_id, bot_id=bot_id, name=name, username=username)
    with Session(engine) as session:
        session.add(lead)
        session.commit()
        session.refresh(lead)
    return lead


def create_message(lead_id: int, sender: str, content: str):
    message = Message(lead_id=lead_id, sender=sender, content=content)
    with Session(engine) as session:
        session.add(message)
        session.commit()
        session.refresh(message)
    return message


def get_conversation_history(lead_id: int, limit: int = 10) -> list[Message]:
    with Session(engine) as session:
        statement = select(Message).where(
            Message.lead_id == lead_id
        ).order_by(Message.timestamp.desc()).limit(limit)
        messages = session.exec(statement).all()
        return list(reversed(messages))


class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        SQLModel.metadata.create_all(self.engine)

    def get_session(self):
        return Session(self.engine)

    def get_or_create_lead(self, bot_id: str, telegram_chat_id: str, name: str = None, username: str = None) -> Lead:
        with self.get_session() as session:
            # Try to find existing lead
            statement = select(Lead).where(
                Lead.bot_id == bot_id,
                Lead.telegram_chat_id == str(telegram_chat_id)
            )
            lead = session.exec(statement).first()

            if not lead:
                # Create new lead
                lead = Lead(
                    bot_id=bot_id,
                    telegram_chat_id=str(telegram_chat_id),
                    name=name,
                    username=username
                )
                session.add(lead)
                session.commit()
                session.refresh(lead)

            return lead

    def save_message(self, lead_id: int, sender: str, content: str) -> Message:
        with self.get_session() as session:
            message = Message(
                lead_id=lead_id,
                sender=sender,
                content=content
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message

    def get_conversation_history(self, lead_id: int, limit: int = 10) -> list[Message]:
        with self.get_session() as session:
            statement = select(Message).where(
                Message.lead_id == lead_id
            ).order_by(Message.timestamp.desc()).limit(limit)
            messages = session.exec(statement).all()
            return list(reversed(messages))