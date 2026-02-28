import os
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import Business, CatalogueItem


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_business(db: AsyncSession, business_id: uuid.UUID) -> Business | None:
    result = await db.execute(
        select(Business)
        .options(selectinload(Business.catalogue_items))
        .where(Business.id == business_id)
    )
    return result.scalar_one_or_none()


async def get_business_by_phone_id(db: AsyncSession, phone_number_id: str) -> Business | None:
    """Return the Business whose phone_number_id matches, with catalogue eagerly loaded.
    If multiple exist (e.g. seeded demo + onboarded), prefer the real one (non-demo)."""
    result = await db.execute(
        select(Business)
        .options(selectinload(Business.catalogue_items))
        .where(Business.phone_number_id == phone_number_id)
        .where(Business.supabase_user_id != "demo-seed")
        .limit(1)
    )
    business = result.scalars().first()
    if business:
        return business
    # Fall back to the seeded demo business if no real business found
    result = await db.execute(
        select(Business)
        .options(selectinload(Business.catalogue_items))
        .where(Business.phone_number_id == phone_number_id)
        .limit(1)
    )
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

async def create_business(db: AsyncSession, data: dict) -> Business:
    """Create and return a new Business from a plain dict of field values."""
    business = Business(
        id=uuid.uuid4(),
        **data,
    )
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


async def add_catalogue_item(
    db: AsyncSession,
    business_id: uuid.UUID,
    item_data: dict,
) -> CatalogueItem:
    """Create and return a CatalogueItem linked to the given business."""
    item = CatalogueItem(
        id=uuid.uuid4(),
        business_id=business_id,
        **item_data,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def seed_demo_business(db: AsyncSession) -> None:
    """
    Create the 'Scented Bliss' demo business and its catalogue on first startup.
    Skips silently if a business with the same phone_number_id already exists.
    """
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")

    # Update access_token on ALL businesses with this phone_number_id
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Business)
        .where(Business.phone_number_id == phone_number_id)
        .values(access_token=access_token)
    )
    await db.commit()

    # Check if any business already exists — if so, skip seeding
    result = await db.execute(
        select(Business).where(Business.phone_number_id == phone_number_id).limit(1)
    )
    if result.scalars().first():
        return

    business = Business(
        id=uuid.uuid4(),
        supabase_user_id="demo-seed",
        name="Scented Bliss",
        whatsapp_number=os.getenv("WHATSAPP_NUMBER", ""),
        phone_number_id=phone_number_id,
        access_token=access_token,
        description=(
            "Scented Bliss is a boutique perfume store offering a curated collection "
            "of luxury and everyday fragrances for men and women."
        ),
        business_hours="Mon–Sat 09:00–18:00",
        location="Cape Town, South Africa",
        payment_methods="EFT, Cash on Delivery, Credit/Debit Card",
        delivery_info="Free delivery on orders over R500. Standard delivery 2–4 business days.",
        greeting_message=(
            "Hi! Welcome to Scented Bliss 🌸 "
            "I'm here to help you find your perfect fragrance. How can I assist you today?"
        ),
        away_message=(
            "Thanks for reaching out to Scented Bliss! "
            "We're currently closed but will respond as soon as we open. "
            "Our hours are Mon–Sat 09:00–18:00."
        ),
        is_active=True,
        ai_enabled=True,
    )
    db.add(business)
    await db.flush()  # get business.id before inserting catalogue items

    catalogue = [
        {
            "name": "Rose Oud Elixir",
            "price": "R850",
            "size": "50ml",
            "description": "A rich blend of Bulgarian rose and smoky oud — bold, warm, and long-lasting.",
            "is_available": True,
        },
        {
            "name": "Citrus Bloom",
            "price": "R490",
            "size": "30ml",
            "description": "Fresh bergamot and white florals for a light, everyday scent.",
            "is_available": True,
        },
        {
            "name": "Midnight Velvet",
            "price": "R1 100",
            "size": "100ml",
            "description": "Dark musk, sandalwood, and amber — a luxurious evening fragrance.",
            "is_available": True,
        },
        {
            "name": "Ocean Breeze",
            "price": "R380",
            "size": "30ml",
            "description": "Crisp aquatic notes with a hint of coconut. Perfect for summer.",
            "is_available": True,
        },
    ]

    for item_data in catalogue:
        db.add(CatalogueItem(id=uuid.uuid4(), business_id=business.id, **item_data))

    await db.commit()
