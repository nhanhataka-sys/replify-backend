import logging
import httpx

logger = logging.getLogger(__name__)

NEWS_API_BASE = "https://newsapi.org/v2"


def _clean_articles(articles: list[dict]) -> list[dict]:
    return [
        {
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "source": a.get("source", {}).get("name", ""),
            "url": a.get("url", ""),
        }
        for a in articles
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


async def fetch_sa_news(api_key: str, page_size: int = 6) -> list[dict]:
    params = {
        "country": "za",
        "pageSize": page_size,
        "apiKey": api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{NEWS_API_BASE}/top-headlines", params=params)
        resp.raise_for_status()
    return _clean_articles(resp.json().get("articles", []))


async def fetch_global_news(api_key: str, page_size: int = 6) -> list[dict]:
    params = {
        "language": "en",
        "pageSize": page_size,
        "apiKey": api_key,
        "category": "general",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{NEWS_API_BASE}/top-headlines", params=params)
        resp.raise_for_status()
    return _clean_articles(resp.json().get("articles", []))
