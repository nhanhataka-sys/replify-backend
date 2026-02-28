import os
import logging
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# ---------------------------------------------------------------------------
# Escalation triggers
# ---------------------------------------------------------------------------

ESCALATION_TRIGGERS: list[str] = [
    "speak to a person",
    "speak to someone",
    "human",
    "agent",
    "manager",
    "complaint",
    "refund",
    "not working",
    "problem",
    "urgent",
    "asap",
    "emergency",
]

HANDOFF_MESSAGE = (
    "I understand — let me connect you with one of our team members who will "
    "be able to assist you further. Please hold on while we get someone for you 🙏"
)

# ---------------------------------------------------------------------------
# Escalation check
# ---------------------------------------------------------------------------

def needs_human_escalation(message: str) -> bool:
    """Return True if the message contains any escalation trigger phrase."""
    lowered = message.lower()
    return any(trigger in lowered for trigger in ESCALATION_TRIGGERS)

# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(business, catalogue_items: list | None = None) -> str:
    """
    Build a personalised system prompt from the business profile and
    available catalogue items.
    """
    lines = [
        f"You are a helpful WhatsApp customer service assistant for *{business.name}*.",
        "",
        "## About the business",
    ]

    if business.description:
        lines.append(f"- Description: {business.description}")
    if business.business_hours:
        lines.append(f"- Business hours: {business.business_hours}")
    if business.location:
        lines.append(f"- Location: {business.location}")
    if business.payment_methods:
        lines.append(f"- Payment methods: {business.payment_methods}")
    if business.delivery_info:
        lines.append(f"- Delivery info: {business.delivery_info}")

    # Catalogue — only items marked as available
    available = [i for i in (catalogue_items or []) if i.is_available]
    if available:
        lines.append("")
        lines.append("## Available products / services")
        for item in available:
            entry = f"- {item.name}"
            if item.price:
                entry += f" | Price: {item.price}"
            if item.size:
                entry += f" | Size: {item.size}"
            if item.description:
                entry += f" | {item.description}"
            lines.append(entry)

    lines += [
        "",
        "## Rules",
        "1. Reply in the same language the customer uses.",
        "2. Keep replies short and friendly — this is WhatsApp, not email.",
        "3. Never make up information that is not listed above.",
        "4. If you cannot confidently answer, reply with exactly: NEEDS_HUMAN",
        "5. When taking an order, always collect the customer's name and delivery address.",
        "6. Do not mention these rules to the customer.",
    ]

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Reply generator
# ---------------------------------------------------------------------------

async def generate_reply(
    customer_message: str,
    business,
    history: list,
    catalogue_items: list | None = None,
) -> tuple[str, bool]:
    """
    Generate an AI reply for an incoming customer message.

    Parameters
    ----------
    customer_message : str
        The latest message from the customer.
    business : Business
        ORM instance for the matched business.
    history : list
        Previous messages as a list of objects with .role and .content
        (or plain dicts with 'role'/'content' keys).
    catalogue_items : list | None
        Pre-loaded CatalogueItem instances (optional).

    Returns
    -------
    (reply_text, needs_human) : tuple[str, bool]
    """

    # 1. Keyword-based escalation check before hitting the API
    if needs_human_escalation(customer_message):
        logger.info("Escalation trigger detected in customer message.")
        return HANDOFF_MESSAGE, True

    # 2. Build conversation history for the API
    api_messages: list[dict] = []
    for msg in history:
        role = msg.role if hasattr(msg, "role") else msg.get("role")
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        if role in ("user", "assistant"):
            api_messages.append({"role": role, "content": content})

    # Append the current customer turn
    api_messages.append({"role": "user", "content": customer_message})

    system_prompt = build_system_prompt(business, catalogue_items)

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=api_messages,
        )

        reply_text: str = response.content[0].text.strip()

        # 3. Check whether the model signalled it cannot handle the query
        if "NEEDS_HUMAN" in reply_text:
            logger.info("Model returned NEEDS_HUMAN signal.")
            return HANDOFF_MESSAGE, True

        return reply_text, False

    except Exception as exc:
        logger.exception("Error generating AI reply: %s", exc)
        return (
            "Sorry, I'm having a little trouble right now. "
            "Please try again in a moment or type 'agent' to speak with someone.",
            False,
        )
