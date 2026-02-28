import os
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from dotenv import load_dotenv

load_dotenv()

from database.connection import init_db, AsyncSessionLocal
from database.models import Business, Conversation, Message, CatalogueItem
from services.business_service import (
    get_business_by_phone_id,
    create_business,
    add_catalogue_item,
    seed_demo_business,
)
from services.conversation_service import (
    get_or_create_conversation,
    save_message,
    get_conversation_history_for_claude,
    flag_for_human,
)
from ai_engine import generate_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_verify_token() -> str:
    return os.getenv("VERIFY_TOKEN", "")
WHATSAPP_API_URL = "https://graph.facebook.com/v19.0"

FALLBACK_MEDIA_MESSAGE = (
    "Hi! I can only process text messages right now. "
    "Please describe what you need and I'll be happy to help 😊"
)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        async with AsyncSessionLocal() as db:
            await seed_demo_business(db)
    except Exception as e:
        logger.warning("DB init skipped (no database connection): %s", e)
    yield


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Replify API", lifespan=lifespan)

allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------

class ReplyBody(BaseModel):
    message: str


class RegisterBusinessBody(BaseModel):
    user_id: str
    name: str
    whatsapp_number: Optional[str] = None
    phone_number_id: Optional[str] = None
    access_token: Optional[str] = None
    description: Optional[str] = None
    business_hours: Optional[str] = None
    location: Optional[str] = None
    payment_methods: Optional[str] = None
    delivery_info: Optional[str] = None
    greeting_message: Optional[str] = None
    away_message: Optional[str] = None
    catalogue: list[dict] = []


# ---------------------------------------------------------------------------
# WhatsApp helpers
# ---------------------------------------------------------------------------

async def send_message(to: str, text: str, phone_number_id: str, access_token: str) -> None:
    url = f"{WHATSAPP_API_URL}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("send_message failed: %s %s", resp.status_code, resp.text)


async def mark_as_read(message_id: str, phone_number_id: str, access_token: str) -> None:
    url = f"{WHATSAPP_API_URL}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning("mark_as_read failed: %s %s", resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WhatsApp webhook
# ---------------------------------------------------------------------------

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta webhook verification handshake."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == get_verify_token():
        logger.info("Webhook verified successfully.")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning("Webhook verification failed. Token mismatch or wrong mode.")
    return Response(content="Forbidden", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Receive and process incoming WhatsApp messages."""
    try:
        body = await request.json()
    except Exception:
        return Response(content="ok", status_code=200)

    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        phone_number_id: str = value.get("metadata", {}).get("phone_number_id", "")
        messages_list = value.get("messages", [])

        if not messages_list:
            return Response(content="ok", status_code=200)

        msg = messages_list[0]
        msg_id: str = msg.get("id", "")
        msg_type: str = msg.get("type", "")
        from_number: str = msg.get("from", "")

        async with AsyncSessionLocal() as db:
            business = await get_business_by_phone_id(db, phone_number_id)
            if not business:
                logger.warning("No business found for phone_number_id=%s", phone_number_id)
                return Response(content="ok", status_code=200)

            await mark_as_read(msg_id, phone_number_id, business.access_token)

            if msg_type == "text":
                customer_text: str = msg.get("text", {}).get("body", "").strip()
                if not customer_text:
                    return Response(content="ok", status_code=200)

                conversation = await get_or_create_conversation(
                    db, business.id, from_number
                )

                await save_message(
                    db,
                    conversation_id=conversation.id,
                    role="user",
                    content=customer_text,
                    whatsapp_message_id=msg_id,
                )

                if business.ai_enabled and conversation.ai_handling:
                    history = get_conversation_history_for_claude(conversation)

                    reply_text, human_needed = await generate_reply(
                        customer_message=customer_text,
                        business=business,
                        history=history,
                        catalogue_items=business.catalogue_items,
                    )

                    await save_message(
                        db,
                        conversation_id=conversation.id,
                        role="assistant",
                        content=reply_text,
                        needs_human=human_needed,
                    )

                    if human_needed:
                        await flag_for_human(db, conversation.id)
                        logger.info("Conversation %s flagged for human handoff.", conversation.id)

                    await send_message(
                        to=from_number,
                        text=reply_text,
                        phone_number_id=phone_number_id,
                        access_token=business.access_token,
                    )

            elif msg_type in ("image", "audio", "video", "document", "sticker"):
                await send_message(
                    to=from_number,
                    text=FALLBACK_MEDIA_MESSAGE,
                    phone_number_id=phone_number_id,
                    access_token=business.access_token,
                )

    except Exception as exc:
        logger.exception("Error processing webhook: %s", exc)

    return Response(content="ok", status_code=200)


# ---------------------------------------------------------------------------
# Dashboard — Conversations
# ---------------------------------------------------------------------------

@app.get("/api/conversations")
async def list_conversations(business_id: str, status: Optional[str] = None):
    """
    Return conversations for a business, optionally filtered by status.
    Each row includes the last message preview and unread flag.
    """
    async with AsyncSessionLocal() as db:
        query = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.business_id == uuid.UUID(business_id))
            .order_by(Conversation.last_message_at.desc())
        )
        if status:
            query = query.where(Conversation.status == status)

        result = await db.execute(query)
        conversations = result.scalars().all()

    rows = []
    for conv in conversations:
        sorted_msgs = sorted(conv.messages, key=lambda m: m.created_at)
        last_msg = sorted_msgs[-1] if sorted_msgs else None
        rows.append({
            "id": str(conv.id),
            "customer_number": conv.customer_number,
            "customer_name": conv.customer_name,
            "status": conv.status,
            "ai_handling": conv.ai_handling,
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "last_message": last_msg.content if last_msg else None,
            "message_count": len(conv.messages),
            "unread": conv.status == "needs_human",
        })

    return rows


@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    """Return all messages for a conversation ordered by created_at."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id))
            .order_by(Message.created_at.asc())
        )
        messages = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "needs_human": m.needs_human,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@app.post("/api/conversations/{conversation_id}/reply")
async def agent_reply(conversation_id: str, body: ReplyBody):
    """Send a human-agent reply via WhatsApp and persist it."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.business))
            .where(Conversation.id == uuid.UUID(conversation_id))
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        business = conversation.business

        await save_message(
            db,
            conversation_id=conversation.id,
            role="human_agent",
            content=body.message,
        )

    await send_message(
        to=conversation.customer_number,
        text=body.message,
        phone_number_id=business.phone_number_id,
        access_token=business.access_token,
    )

    return {"status": "sent"}


@app.post("/api/conversations/{conversation_id}/takeover")
async def takeover_conversation(conversation_id: str):
    """Disable AI and flag the conversation for a human agent."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Conversation not found")

        await flag_for_human(db, uuid.UUID(conversation_id))

    return {"status": "takeover_complete"}


@app.post("/api/conversations/{conversation_id}/resolve")
async def resolve_conversation(conversation_id: str):
    """Mark a conversation as resolved and disable AI handling."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Conversation not found")

        await db.execute(
            update(Conversation)
            .where(Conversation.id == uuid.UUID(conversation_id))
            .values(status="resolved", ai_handling=False)
        )
        await db.commit()

    return {"status": "resolved"}


# ---------------------------------------------------------------------------
# Dashboard — Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats(business_id: str):
    """Return conversation counts grouped by status for a business."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation.status, func.count(Conversation.id).label("count"))
            .where(Conversation.business_id == uuid.UUID(business_id))
            .group_by(Conversation.status)
        )
        rows = result.all()

    counts = {row.status: row.count for row in rows}
    total = sum(counts.values())

    return {
        "total": total,
        "open": counts.get("open", 0),
        "needs_human": counts.get("needs_human", 0),
        "resolved": counts.get("resolved", 0),
    }


# ---------------------------------------------------------------------------
# Dashboard — Business
# ---------------------------------------------------------------------------

@app.post("/api/businesses/register")
async def register_business(body: RegisterBusinessBody):
    """Register a new business account and seed its catalogue."""
    async with AsyncSessionLocal() as db:
        # Check for duplicate supabase_user_id
        existing = await db.execute(
            select(Business).where(Business.supabase_user_id == body.user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Business already registered for this user")

        business_data = {
            "supabase_user_id": body.user_id,
            "name": body.name,
            "whatsapp_number": body.whatsapp_number,
            "phone_number_id": body.phone_number_id,
            "access_token": body.access_token,
            "description": body.description,
            "business_hours": body.business_hours,
            "location": body.location,
            "payment_methods": body.payment_methods,
            "delivery_info": body.delivery_info,
            "greeting_message": body.greeting_message,
            "away_message": body.away_message,
            "is_active": True,
            "ai_enabled": True,
        }

        business = await create_business(db, business_data)

        for item in body.catalogue:
            await add_catalogue_item(db, business.id, item)

    return {"business_id": str(business.id)}


@app.get("/api/businesses/me")
async def get_my_business(user_id: str):
    """Return the business linked to a Supabase user_id."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Business)
            .options(selectinload(Business.catalogue_items))
            .where(Business.supabase_user_id == user_id)
        )
        business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="No business found for this user")

    return {
        "id": str(business.id),
        "name": business.name,
        "whatsapp_number": business.whatsapp_number,
        "phone_number_id": business.phone_number_id,
        "description": business.description,
        "business_hours": business.business_hours,
        "location": business.location,
        "payment_methods": business.payment_methods,
        "delivery_info": business.delivery_info,
        "greeting_message": business.greeting_message,
        "away_message": business.away_message,
        "is_active": business.is_active,
        "ai_enabled": business.ai_enabled,
        "created_at": business.created_at.isoformat(),
        "catalogue": [
            {
                "id": str(i.id),
                "name": i.name,
                "price": i.price,
                "size": i.size,
                "description": i.description,
                "is_available": i.is_available,
            }
            for i in business.catalogue_items
        ],
    }
