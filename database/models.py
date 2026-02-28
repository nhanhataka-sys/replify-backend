import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.connection import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supabase_user_id = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    whatsapp_number = Column(String, nullable=True)
    phone_number_id = Column(String, nullable=True)
    access_token = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    business_hours = Column(Text, nullable=True)
    location = Column(Text, nullable=True)
    payment_methods = Column(Text, nullable=True)
    delivery_info = Column(Text, nullable=True)
    greeting_message = Column(Text, nullable=True)
    away_message = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    ai_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    catalogue_items = relationship("CatalogueItem", back_populates="business", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="business", cascade="all, delete-orphan")


class CatalogueItem(Base):
    __tablename__ = "catalogue_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(String, nullable=True)
    size = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    is_available = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    business = relationship("Business", back_populates="catalogue_items")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    customer_number = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="open")  # open | needs_human | resolved
    ai_handling = Column(Boolean, nullable=False, default=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    business = relationship("Business", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # user | assistant | human_agent
    content = Column(Text, nullable=False)
    whatsapp_message_id = Column(String, nullable=True, unique=True)
    needs_human = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
