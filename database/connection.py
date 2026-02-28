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
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _make_engine():
    raw_url = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not raw_url:
        raise RuntimeError(
            "Database URL not configured. "
            "Set SUPABASE_DATABASE_URL in Railway Variables."
        )
    return create_async_engine(
        _build_async_url(raw_url),
        echo=False,
        connect_args={"statement_cache_size": 0},
    )


# Lazy — engine and session factory created on first use, not at import time
_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def AsyncSessionLocal():
    """Return a new AsyncSession. Used as: async with AsyncSessionLocal() as db:"""
    return _get_session_factory()()


async def get_db():
    async with _get_session_factory()() as session:
        yield session


async def init_db():
    import database.models  # noqa: F401 — ensures all models are registered on Base
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
