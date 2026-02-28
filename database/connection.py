import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase


class Base(DeclarativeBase):
    pass


def _build_async_url(url: str) -> str:
    """Ensure the DATABASE_URL uses the asyncpg driver."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        # Heroku-style shorthand
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# Check SUPABASE_DATABASE_URL first (avoids Railway auto-injecting its own DATABASE_URL)
_raw_db_url = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL", "")
if not _raw_db_url:
    raise RuntimeError(
        "Neither SUPABASE_DATABASE_URL nor DATABASE_URL is set. "
        "Please add SUPABASE_DATABASE_URL in Railway → Variables."
    )
DATABASE_URL = _build_async_url(_raw_db_url)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    import database.models  # noqa: F401 — ensures all models are registered on Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
