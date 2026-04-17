import logging
import httpx

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v19.0"


async def send_bulletin(
    message: str,
    recipients: list[str],
    phone_number_id: str,
    access_token: str,
) -> list[str]:
    """Send the bulletin to each recipient. Returns list of numbers successfully delivered."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    sent: list[str] = []

    async with httpx.AsyncClient(timeout=15) as client:
        for number in recipients:
            payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": message, "preview_url": False},
            }
            resp = await client.post(
                f"{WHATSAPP_API_URL}/{phone_number_id}/messages",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                sent.append(number)
                logger.info("Bulletin sent to %s", number)
            else:
                logger.error(
                    "Failed to send bulletin to %s: %s %s",
                    number, resp.status_code, resp.text,
                )

    return sent
