import logging
import httpx

logger = logging.getLogger(__name__)

GNEWS_BASE = "https://gnews.io/api/v4/top-headlines"


def _clean(articles: list[dict]) -> list[dict]:
    return [
        {
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "source": a.get("source", {}).get("name", ""),
            "url": a.get("url", ""),
        }
        for a in articles
        if a.get("title")
    ]


async def fetch_sa_news(api_key: str, page_size: int = 6) -> list[dict]:
    params = {"country": "za", "max": page_size, "token": api_key}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(GNEWS_BASE, params=params)
        resp.raise_for_status()
    return _clean(resp.json().get("articles", []))


async def fetch_global_news(api_key: str, page_size: int = 6) -> list[dict]:
    params = {"lang": "en", "max": page_size, "token": api_key, "topic": "world"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(GNEWS_BASE, params=params)
        resp.raise_for_status()
    return _clean(resp.json().get("articles", []))
