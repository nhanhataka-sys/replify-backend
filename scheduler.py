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
    from services.bulletin_service import generate_bulletin_thread
    from services.twitter_service import post_thread
    from database.connection import AsyncSessionLocal
    from database.models import NewsBulletin

    logger.info("Daily bulletin job started")

    news_api_key = os.getenv("NEWS_API_KEY", "")
    if not news_api_key:
        logger.warning("NEWS_API_KEY not set — skipping bulletin")
        return

    sa_articles: list[dict] = []
    global_articles: list[dict] = []
    tweets: list[str] = []
    tweet_ids: list[str] | None = None
    posted = False
    posted_at: datetime | None = None
    error_message: str | None = None

    try:
        sa_articles, global_articles = await asyncio.gather(
            fetch_sa_news(news_api_key),
            fetch_global_news(news_api_key),
        )
        logger.info("Fetched %d SA and %d global articles", len(sa_articles), len(global_articles))

        tweets = await generate_bulletin_thread(sa_articles, global_articles)
        logger.info("Generated %d-tweet bulletin", len(tweets))

        twitter_key = os.getenv("TWITTER_API_KEY")
        twitter_secret = os.getenv("TWITTER_API_SECRET")
        twitter_at = os.getenv("TWITTER_ACCESS_TOKEN")
        twitter_at_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

        if all([twitter_key, twitter_secret, twitter_at, twitter_at_secret]):
            tweet_ids = await asyncio.to_thread(
                post_thread,
                tweets,
                api_key=twitter_key,
                api_secret=twitter_secret,
                access_token=twitter_at,
                access_token_secret=twitter_at_secret,
            )
            posted = True
            posted_at = datetime.utcnow()
            logger.info("Bulletin posted as thread of %d tweets", len(tweet_ids))
        else:
            logger.warning("Twitter credentials not fully configured — bulletin saved but not posted")

    except Exception as exc:
        error_message = str(exc)
        logger.exception("Daily bulletin job failed: %s", exc)

    if tweets or error_message:
        try:
            async with AsyncSessionLocal() as db:
                bulletin = NewsBulletin(
                    bulletin_date=date.today(),
                    tweets=tweets,
                    tweet_ids=tweet_ids,
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
