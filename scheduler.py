import asyncio
import logging
import os
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Runs daily at BULLETIN_HOUR:BULLETIN_MINUTE SAST (Africa/Johannesburg = UTC+2)
scheduler = AsyncIOScheduler(timezone="Africa/Johannesburg")


async def run_daily_bulletin() -> None:
    from services.news_service import fetch_sa_news, fetch_global_news
    from services.bulletin_service import generate_bulletin
    from services.whatsapp_bulletin_service import send_bulletin
    from database.connection import AsyncSessionLocal
    from database.models import NewsBulletin

    logger.info("Daily bulletin job started")

    sa_articles: list[dict] = []
    global_articles: list[dict] = []
    message = ""
    sent_to: list[str] = []
    posted = False
    posted_at: datetime | None = None
    error_message: str | None = None

    try:
        sa_articles, global_articles = await asyncio.gather(
            fetch_sa_news(),
            fetch_global_news(),
        )
        logger.info("Fetched %d SA and %d global articles", len(sa_articles), len(global_articles))

        message = await generate_bulletin(sa_articles, global_articles)
        logger.info("Bulletin generated (%d chars)", len(message))

        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        recipients_raw = os.getenv("BULLETIN_WHATSAPP_TO", "")
        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

        if phone_number_id and access_token and recipients:
            sent_to = await send_bulletin(message, recipients, phone_number_id, access_token)
            posted = bool(sent_to)
            posted_at = datetime.utcnow() if posted else None
            logger.info("Bulletin sent to %d/%d recipients", len(sent_to), len(recipients))
        else:
            logger.warning(
                "WhatsApp credentials or BULLETIN_WHATSAPP_TO not configured — "
                "bulletin generated but not sent"
            )

    except Exception as exc:
        error_message = str(exc)
        logger.exception("Daily bulletin job failed: %s", exc)

    if message or error_message:
        try:
            async with AsyncSessionLocal() as db:
                bulletin = NewsBulletin(
                    bulletin_date=date.today(),
                    tweets=[message] if message else [],   # single message stored in list
                    tweet_ids=sent_to or None,
                    sa_articles=sa_articles,
                    global_articles=global_articles,
                    posted=posted,
                    posted_at=posted_at,
                    error_message=error_message,
                )
                db.add(bulletin)
                await db.commit()
                logger.info("Bulletin record saved to DB")
        except Exception as db_exc:
            logger.exception("Failed to save bulletin to DB: %s", db_exc)


def start_scheduler() -> None:
    hour = int(os.getenv("BULLETIN_HOUR", "8"))
    minute = int(os.getenv("BULLETIN_MINUTE", "0"))
    scheduler.add_job(
        run_daily_bulletin,
        trigger="cron",
        hour=hour,
        minute=minute,
        id="daily_bulletin",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("News bulletin scheduler started — fires daily at %02d:%02d SAST", hour, minute)


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("News bulletin scheduler stopped")
