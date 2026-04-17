import asyncio
import logging
import feedparser

logger = logging.getLogger(__name__)

# Free RSS feeds — no API key required
SA_FEEDS = [
    ("News24",        "https://feeds.news24.com/articles/news24/TopStories/rss"),
    ("TimesLive",     "https://www.timeslive.co.za/rss/"),
    ("Daily Maverick","https://www.dailymaverick.co.za/feed/"),
    ("SABC News",     "https://www.sabcnews.com/sabcnews/feed/"),
]

GLOBAL_FEEDS = [
    ("BBC News",   "http://feeds.bbci.co.uk/news/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Sky News",   "https://feeds.skynews.com/feeds/rss/world.xml"),
]


def _parse_feed(source: str, url: str, limit: int = 3) -> list[dict]:
    """Fetch and parse a single RSS feed synchronously (run in thread)."""
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            if not title or "[Removed]" in title:
                continue
            articles.append({
                "title": title,
                "description": entry.get("summary", "").strip(),
                "source": source,
                "url": entry.get("link", ""),
            })
        return articles
    except Exception as exc:
        logger.warning("Failed to parse feed %s: %s", url, exc)
        return []


async def _fetch_feeds(feeds: list[tuple[str, str]], total: int = 6) -> list[dict]:
    """Fetch multiple RSS feeds concurrently and return up to `total` articles."""
    tasks = [
        asyncio.to_thread(_parse_feed, source, url)
        for source, url in feeds
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    articles: list[dict] = []
    for result in results:
        if isinstance(result, list):
            articles.extend(result)
        if len(articles) >= total:
            break

    return articles[:total]


async def fetch_sa_news(page_size: int = 6) -> list[dict]:
    return await _fetch_feeds(SA_FEEDS, total=page_size)


async def fetch_global_news(page_size: int = 6) -> list[dict]:
    return await _fetch_feeds(GLOBAL_FEEDS, total=page_size)
