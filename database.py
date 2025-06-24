import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlmodel import select, Session
from models import Lead, Message

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
