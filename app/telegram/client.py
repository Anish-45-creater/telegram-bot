"""
app/telegram/client.py — Telegram Bot API integration.

Sends plain text messages (no MarkdownV2) to avoid escaping issues
with addresses, phone numbers, and special characters in business data.
"""
import logging
import requests
from config.settings import settings

logger = logging.getLogger(__name__)

TG_BASE = "https://api.telegram.org/bot{token}"


def _base_url() -> str:
    return TG_BASE.format(token=settings.TELEGRAM_BOT_TOKEN)


def send_telegram_message(chat_id: str | int, text: str) -> bool:
    """
    Send a plain text message to a Telegram chat.
    Splits automatically at 4000 chars if the message is long.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured.")
        return False

    # Split into chunks of 4000 chars
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    url = f"{_base_url()}/sendMessage"
    success = True

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            # plain text — no parse_mode — safest for business data with
            # special chars in addresses, phone numbers, etc.
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            logger.info("Sent message to %s (%d chars)", chat_id, len(chunk))
        except Exception as exc:
            logger.exception("Failed to send message to %s: %s", chat_id, exc)
            success = False

    return success


def parse_incoming_update(payload: dict) -> list[dict]:
    """
    Parse a Telegram Update object (webhook POST body).
    Returns list of message dicts with from_phone, name, text, chat_id.
    """
    messages = []
    try:
        msg = payload.get("message") or payload.get("channel_post")
        if not msg:
            return messages

        text = (msg.get("text") or "").strip()
        if not text:
            return messages

        chat = msg.get("chat", {})
        sender = msg.get("from", {}) or chat

        chat_id = chat.get("id")
        first = sender.get("first_name", "")
        last = sender.get("last_name", "")
        username = sender.get("username", "")
        full_name = f"{first} {last}".strip() or username or str(chat_id)

        messages.append({
            "from_phone": str(chat_id),
            "name": full_name,
            "text": text,
            "message_id": msg.get("message_id"),
            "chat_id": chat_id,
        })
    except Exception as exc:
        logger.exception("Failed to parse Telegram update: %s", exc)

    return messages
