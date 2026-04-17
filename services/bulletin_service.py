import json
import logging
import os
from datetime import date

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


async def generate_bulletin_thread(
    sa_articles: list[dict],
    global_articles: list[dict],
    today: date | None = None,
) -> list[str]:
    if today is None:
        today = date.today()

    date_str = today.strftime("%A, %d %B %Y")

    sa_text = "\n".join(
        f"- {a['title']} ({a['source']})" for a in sa_articles[:6] if a.get("title")
    ) or "No SA articles available."

    global_text = "\n".join(
        f"- {a['title']} ({a['source']})" for a in global_articles[:6] if a.get("title")
    ) or "No global articles available."

    prompt = f"""You are crafting a daily news bulletin thread for X (Twitter).

Today: {date_str}

South African news headlines:
{sa_text}

Global news headlines:
{global_text}

Create a thread of exactly 4 tweets following these rules:
1. Tweet 1 — Header: engaging opener with date, 🇿🇦🌍 emojis, mention it's a morning briefing thread (🧵)
2. Tweet 2 — SA section: label "🇿🇦 SOUTH AFRICA" then 3-4 bullet points (•) with concise summaries
3. Tweet 3 — Global section: label "🌍 WORLD NEWS" then 3-4 bullet points (•) with concise summaries
4. Tweet 4 — Footer: closing line + 5-6 relevant hashtags (#SANews #SouthAfrica #WorldNews etc.)

CRITICAL constraints:
- Every tweet MUST be ≤ 280 characters — count carefully before finalising
- No URLs in any tweet
- Keep bullet points short (one sentence each)
- Be factual and neutral in tone

Return ONLY a valid JSON array of exactly 4 tweet strings, with no extra text or markdown fences.
Example format: ["tweet1", "tweet2", "tweet3", "tweet4"]"""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude wraps the JSON
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    tweets: list[str] = json.loads(raw)

    # Safety net: enforce 280-char limit
    for i, tweet in enumerate(tweets):
        if len(tweet) > 280:
            tweets[i] = tweet[:277] + "..."
            logger.warning("Tweet %d truncated to fit 280-char limit", i + 1)

    return tweets
