"""
app/telegram/client.py
Handles sending messages AND parsing incoming updates including location sharing.
"""
import logging, requests
from config.settings import settings

logger = logging.getLogger(__name__)
TG_BASE = "https://api.telegram.org/bot{token}"

def _url(): return TG_BASE.format(token=settings.TELEGRAM_BOT_TOKEN)

def send_telegram_message(chat_id, text: str) -> bool:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set"); return False
    url = f"{_url()}/sendMessage"
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": chunk}, timeout=10).raise_for_status()
            logger.info("Sent to %s (%d chars)", chat_id, len(chunk))
        except Exception as e:
            logger.exception("Send failed: %s", e); return False
    return True

def send_location_request(chat_id) -> bool:
    """Send a button asking the user to share their live location."""
    if not settings.TELEGRAM_BOT_TOKEN: return False
    payload = {
        "chat_id": chat_id,
        "text": "📍 Share your location so I can find nearby businesses!",
        "reply_markup": {
            "keyboard": [[{"text": "📍 Share my location", "request_location": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
    }
    try:
        requests.post(f"{_url()}/sendMessage", json=payload, timeout=10).raise_for_status()
        return True
    except Exception as e:
        logger.exception("Location request failed: %s", e); return False

def parse_incoming_update(payload: dict) -> list[dict]:
    """
    Parse Telegram Update. Handles:
    - text messages
    - location messages (user shared GPS)
    """
    messages = []
    try:
        msg = payload.get("message") or payload.get("channel_post")
        if not msg: return messages

        chat   = msg.get("chat", {})
        sender = msg.get("from", {}) or chat
        chat_id = chat.get("id")
        first   = sender.get("first_name", "")
        last    = sender.get("last_name", "")
        username = sender.get("username", "")
        full_name = f"{first} {last}".strip() or username or str(chat_id)

        base = {"from_phone": str(chat_id), "name": full_name,
                "chat_id": chat_id, "message_id": msg.get("message_id"),
                "lat": None, "lng": None}

        # Location message
        if msg.get("location"):
            loc = msg["location"]
            base["text"]  = "__location__"
            base["lat"]   = loc.get("latitude")
            base["lng"]   = loc.get("longitude")
            messages.append(base)
        # Text message
        elif msg.get("text","").strip():
            base["text"] = msg["text"].strip()
            messages.append(base)

    except Exception as e:
        logger.exception("Parse update failed: %s", e)
    return messages
