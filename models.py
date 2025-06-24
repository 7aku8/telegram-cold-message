from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bot_id: str
    telegram_chat_id: str
    name: Optional[str] = None
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    messages: List["Message"] = Relationship(back_populates="lead")


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(default=None, foreign_key="lead.id")
    sender: str  # 'bot' or 'user'
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    lead: Lead = Relationship(back_populates="messages")