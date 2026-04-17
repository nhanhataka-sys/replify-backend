import logging
import os
from datetime import date

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


async def generate_bulletin(
    sa_articles: list[dict],
    global_articles: list[dict],
    today: date | None = None,
) -> str:
    """Generate a WhatsApp-formatted daily news bulletin. Returns a single message string."""
    if today is None:
        today = date.today()

    date_str = today.strftime("%A, %d %B %Y")

    sa_text = "\n".join(
        f"- {a['title']} ({a['source']})" for a in sa_articles[:6] if a.get("title")
    ) or "No SA articles available."

    global_text = "\n".join(
        f"- {a['title']} ({a['source']})" for a in global_articles[:6] if a.get("title")
    ) or "No global articles available."

    prompt = f"""You are writing a daily WhatsApp news bulletin.

Today: {date_str}

South African news headlines:
{sa_text}

Global news headlines:
{global_text}

Write a single WhatsApp message following this exact structure:

🗞️ *Daily News Bulletin*
📅 *{date_str}*

🇿🇦 *SOUTH AFRICA*
• [concise summary of story 1]
• [concise summary of story 2]
• [concise summary of story 3]
• [concise summary of story 4]

🌍 *WORLD NEWS*
• [concise summary of story 1]
• [concise summary of story 2]
• [concise summary of story 3]
• [concise summary of story 4]

_Stay informed_ 📲

Rules:
- Use *bold* for section headers (wrap in asterisks)
- Each bullet point must be one concise sentence (under 100 chars)
- Be factual and neutral
- No URLs
- Total message must be under 3000 characters

Return only the message text, no extra commentary."""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()
