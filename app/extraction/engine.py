"""
app/extraction/engine.py — Layer 4: Extraction & Validation Engine.

Takes raw results from any tool and returns a clean, deduplicated,
validated list of structured records.
"""
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ─── Validation patterns ──────────────────────────────────────────────────────

PHONE_PATTERNS = [
    re.compile(r"^(\+91[\s\-]?)?[6-9]\d{9}$"),                    # Indian mobile
    re.compile(r"^\+?[1-9]\d{6,14}$"),                             # generic intl
    re.compile(r"^\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}$"),         # US/CA format
]

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

SPAM_KEYWORDS = {
    "advertisement", "sponsored", "ad ", "click here", "subscribe",
    "buy now", "download now", "limited offer",
}


def _is_valid_phone(phone: str) -> bool:
    if not phone:
        return False
    cleaned = re.sub(r"[\s\-\(\)]", "", str(phone))
    return any(p.match(cleaned) for p in PHONE_PATTERNS)


def _clean_phone(phone: str) -> str:
    """Normalise phone: strip spaces/dashes, ensure +91 prefix for Indian numbers."""
    cleaned = re.sub(r"[\s\-\(\)]", "", str(phone))
    if re.match(r"^[6-9]\d{9}$", cleaned):
        cleaned = "+91" + cleaned
    return cleaned


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(str(email))) if email else False


def _is_valid_website(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        return bool(parsed.netloc) and "." in parsed.netloc
    except Exception:
        return False


def _is_spam(entry: dict) -> bool:
    text = " ".join(str(v) for v in entry.values()).lower()
    return any(kw in text for kw in SPAM_KEYWORDS)


def _deduplicate(entries: list[dict]) -> list[dict]:
    """Remove duplicates based on name + phone or name + website."""
    seen: set = set()
    unique = []
    for e in entries:
        key = (
            (e.get("name") or "").lower().strip(),
            (e.get("phone") or e.get("website") or e.get("linkedin_url") or "").lower(),
        )
        if key not in seen and key != ("", ""):
            seen.add(key)
            unique.append(e)
    return unique


def clean_results(raw: list[dict]) -> list[dict]:
    """
    Full extraction pipeline:
      1. Remove spam entries
      2. Validate + clean phone numbers
      3. Validate emails and websites
      4. Deduplicate
      5. Remove empty / useless entries

    Returns a clean list, max 10 entries.
    """
    cleaned = []
    for entry in raw:
        if _is_spam(entry):
            continue

        record: dict = {}

        # Name
        name = str(entry.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
        record["name"] = name

        # Phone
        raw_phone = str(entry.get("phone") or "")
        if _is_valid_phone(raw_phone):
            record["phone"] = _clean_phone(raw_phone)
        else:
            record["phone"] = ""

        # Website
        website = str(entry.get("website") or "")
        record["website"] = website if _is_valid_website(website) else ""

        # LinkedIn URL (people search)
        if entry.get("linkedin_url"):
            record["linkedin_url"] = entry["linkedin_url"]

        # Address
        if entry.get("address"):
            record["address"] = str(entry["address"])[:100]

        # Rating
        if entry.get("rating"):
            record["rating"] = entry["rating"]

        # Email
        email = str(entry.get("email") or "")
        if _is_valid_email(email):
            record["email"] = email

        # Snippet / headline (for news / people)
        if entry.get("snippet"):
            record["snippet"] = str(entry["snippet"])[:200]
        if entry.get("headline"):
            record["headline"] = str(entry["headline"])[:200]

        # Source
        record["source"] = entry.get("source", "")

        # Published (news)
        if entry.get("published"):
            record["published"] = entry["published"]
        if entry.get("source_name"):
            record["source_name"] = entry["source_name"]

        cleaned.append(record)

    deduped = _deduplicate(cleaned)
    logger.info("Extraction: %d raw → %d clean records", len(raw), len(deduped))
    return deduped[:10]
