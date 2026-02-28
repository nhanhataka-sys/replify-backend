import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import Conversation, Message


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

async def get_or_create_conversation(
    db: AsyncSession,
    business_id: uuid.UUID,
    customer_number: str,
) -> Conversation:
    """
    Return the most recent open/needs_human conversation for this customer,
    or create a fresh one if none exists.
    Messages are eagerly loaded so the returned object can be used directly
    by get_conversation_history_for_claude without further queries.
    """
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.business_id == business_id,
            Conversation.customer_number == customer_number,
            Conversation.status != "resolved",
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(
            id=uuid.uuid4(),
            business_id=business_id,
            customer_number=customer_number,
            status="open",
            ai_handling=True,
            last_message_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    return conversation


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

async def save_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    whatsapp_message_id: str | None = None,
    needs_human: bool = False,
) -> Message:
    """
    Persist a message and keep the parent conversation's timestamps and
    status in sync.

    - Always updates last_message_at to now.
    - If needs_human=True, sets conversation status → 'needs_human'.
    - If the conversation was 'open' and this is a new inbound message,
      status stays 'open'.
    """
    now = datetime.now(timezone.utc)

    message = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        whatsapp_message_id=whatsapp_message_id,
        needs_human=needs_human,
        created_at=now,
    )
    db.add(message)

    # Build the update values for the parent conversation
    conv_updates: dict = {"last_message_at": now}
    if needs_human:
        conv_updates["status"] = "needs_human"
        conv_updates["ai_handling"] = False

    await db.execute(
        Conversation.__table__.update()
        .where(Conversation.id == conversation_id)
        .values(**conv_updates)
    )

    await db.commit()
    await db.refresh(message)
    return message


# ---------------------------------------------------------------------------
# History helper (sync — messages must already be loaded)
# ---------------------------------------------------------------------------

def get_conversation_history_for_claude(conversation: Conversation) -> list[dict]:
    """
    Return a list of {role, content} dicts containing only 'user' and
    'assistant' messages, ordered by created_at.

    Requires conversation.messages to have been eagerly loaded
    (e.g. via selectinload in get_or_create_conversation).
    """
    history = []
    for msg in sorted(conversation.messages, key=lambda m: m.created_at):
        if msg.role in ("user", "assistant"):
            history.append({"role": msg.role, "content": msg.content})
    return history


# ---------------------------------------------------------------------------
# Human handoff
# ---------------------------------------------------------------------------

async def flag_for_human(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    """Mark a conversation as needing a human agent and disable AI handling."""
    await db.execute(
        Conversation.__table__.update()
        .where(Conversation.id == conversation_id)
        .values(status="needs_human", ai_handling=False)
    )
    await db.commit()
