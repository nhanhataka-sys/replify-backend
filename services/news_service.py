import asyncio
import logging
from xml.etree import ElementTree as ET
import httpx

logger = logging.getLogger(__name__)

# Free RSS feeds — no API key required
SA_FEEDS = [
    ("News24",         "https://feeds.news24.com/articles/news24/TopStories/rss"),
    ("TimesLive",      "https://www.timeslive.co.za/rss/"),
    ("Daily Maverick", "https://www.dailymaverick.co.za/feed/"),
    ("SABC News",      "https://www.sabcnews.com/sabcnews/feed/"),
]

GLOBAL_FEEDS = [
    ("BBC News",   "http://feeds.bbci.co.uk/news/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Sky News",   "https://feeds.skynews.com/feeds/rss/world.xml"),
]


def _strip_cdata(text: str) -> str:
    if text and text.startswith("<![CDATA["):
        return text[9:-3].strip()
    return (text or "").strip()


async def _fetch_feed(source: str, url: str, limit: int = 3) -> list[dict]:
    """Fetch and parse a single RSS feed. Returns up to `limit` articles."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

        root = ET.fromstring(resp.content)
        # Handle both RSS <item> and Atom <entry> formats
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        articles = []
        for item in items[:limit]:
            title = _strip_cdata(
                item.findtext("title") or item.findtext("atom:title", namespaces=ns) or ""
            )
            if not title or "[Removed]" in title:
                continue
            articles.append({
                "title": title,
                "description": _strip_cdata(
                    item.findtext("description")
                    or item.findtext("atom:summary", namespaces=ns)
                    or ""
                ),
                "source": source,
                "url": (
                    item.findtext("link")
                    or item.findtext("atom:link", namespaces=ns)
                    or ""
                ),
            })
        return articles

    except Exception as exc:
        logger.warning("Feed %s failed: %s", url, exc)
        return []


async def fetch_sa_news(page_size: int = 6) -> list[dict]:
    results = await asyncio.gather(*[
        _fetch_feed(source, url) for source, url in SA_FEEDS
    ], return_exceptions=True)
    articles: list[dict] = []
    for r in results:
        if isinstance(r, list):
            articles.extend(r)
        if len(articles) >= page_size:
            break
    return articles[:page_size]


async def fetch_global_news(page_size: int = 6) -> list[dict]:
    results = await asyncio.gather(*[
        _fetch_feed(source, url) for source, url in GLOBAL_FEEDS
    ], return_exceptions=True)
    articles: list[dict] = []
    for r in results:
        if isinstance(r, list):
            articles.extend(r)
        if len(articles) >= page_size:
            break
    return articles[:page_size]
