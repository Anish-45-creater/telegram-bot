"""
app/agent/searcher.py

Pipeline (all 100% free):
  1. SerpAPI google_maps engine  → real name, phone, address, rating, reviews
  2. If Maps gives < 3 results   → SerpAPI google_local_results as fallback
  3. Gemini 1.5 Flash (free tier, NO grounding) → detects location/category
     from the query and formats a clean summary

Free limits:
  SerpAPI  : 100 searches / month free
  Gemini   : 1,500 requests / day free, 15 req/min free
"""
import json
import logging
import re
import requests
from config.settings import settings

logger = logging.getLogger(__name__)

SERPAPI_BASE = "https://serpapi.com/search.json"
GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={key}"
)

# ─── Gemini: extract location + category from the query ──────────────────────

def _parse_query(user_query: str) -> dict:
    """
    Ask Gemini (free, no grounding) to extract:
      - location  : city/area mentioned in the query
      - category  : type of business
      - count     : how many results user wants (default 10)
      - maps_query: optimised query string for Google Maps search

    Returns dict with those keys.
    """
    if not settings.GEMINI_API_KEY:
        return {
            "location": "",
            "category": user_query,
            "count": 10,
            "maps_query": user_query,
        }

    prompt = f"""Extract search parameters from this business query.
Return ONLY valid JSON, no explanation, no markdown.

Query: "{user_query}"

Return:
{{
  "location": "city or area name, empty string if not mentioned",
  "category": "type of business or service",
  "count": <number of results requested, default 10, max 20>,
  "maps_query": "optimised short query for Google Maps e.g. 'electricians Chennai'"
}}"""

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generation_config": {"temperature": 0, "max_output_tokens": 256},
    }
    try:
        r = requests.post(
            GEMINI_URL.format(key=settings.GEMINI_API_KEY),
            json=payload, timeout=15,
        )
        r.raise_for_status()
        raw = ""
        for part in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
            raw += part.get("text", "")
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Gemini parse_query failed: %s", exc)
        # Fallback: crude extraction
        count_match = re.search(r"\b(\d+)\b", user_query)
        return {
            "location": "",
            "category": user_query,
            "count": int(count_match.group(1)) if count_match else 10,
            "maps_query": user_query,
        }


# ─── SerpAPI: Google Maps search ─────────────────────────────────────────────

def _maps_search(maps_query: str, count: int) -> list[dict]:
    """
    SerpAPI google_maps engine.
    Returns list of raw place dicts with: title, phone, address, rating,
    reviews, website, type.
    """
    if not settings.SERPAPI_KEY:
        logger.error("SERPAPI_KEY not set")
        return []

    params = {
        "engine":  "google_maps",
        "q":       maps_query,
        "type":    "search",
        "hl":      "en",
        "gl":      "in",
        "api_key": settings.SERPAPI_KEY,
    }
    try:
        r = requests.get(SERPAPI_BASE, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        raw = data.get("local_results", [])
        logger.info("Maps returned %d results for '%s'", len(raw), maps_query)
        return raw[:count]
    except Exception as exc:
        logger.exception("SerpAPI Maps failed: %s", exc)
        return []


def _local_search_fallback(maps_query: str, count: int) -> list[dict]:
    """
    Fallback: SerpAPI organic search → local pack results.
    Used when Maps returns < 3 results.
    """
    if not settings.SERPAPI_KEY:
        return []
    params = {
        "engine":  "google",
        "q":       f"{maps_query} contact phone number",
        "hl":      "en",
        "gl":      "in",
        "num":     20,
        "api_key": settings.SERPAPI_KEY,
    }
    try:
        r = requests.get(SERPAPI_BASE, params=params, timeout=20)
        r.raise_for_status()
        data   = r.json()
        places = data.get("local_results", [])
        logger.info("Fallback local pack: %d results", len(places))
        return places[:count]
    except Exception as exc:
        logger.exception("SerpAPI fallback failed: %s", exc)
        return []


# ─── Normalise a raw SerpAPI place into a clean dict ─────────────────────────

def _normalise(place: dict) -> dict:
    phone = (
        place.get("phone") or
        place.get("extensions", {}).get("phone", "") or
        ""
    )
    rating  = place.get("rating", "")
    reviews = place.get("reviews", "")
    return {
        "name":    place.get("title", ""),
        "phone":   phone,
        "address": place.get("address", ""),
        "rating":  str(rating)  if rating  else "",
        "reviews": str(reviews) if reviews else "",
        "website": place.get("website", ""),
        "type":    place.get("type", ""),
    }


# ─── Public entry point ───────────────────────────────────────────────────────

def search_businesses(user_query: str, count: int = 10) -> dict:
    """
    Full pipeline:
      1. Gemini parses the query → location, category, maps_query
      2. SerpAPI Maps search → real business data
      3. Fallback if needed
      4. Return structured dict ready for responder.py

    Returns:
    {
      "query":    original user query,
      "location": detected location,
      "category": detected category,
      "results":  [ {name, phone, address, rating, reviews, website, type}, ... ],
      "error":    "" or error message
    }
    """
    # Step 1 — parse query
    parsed = _parse_query(user_query)
    location   = parsed.get("location", "")
    category   = parsed.get("category", user_query)
    maps_query = parsed.get("maps_query", user_query)
    count      = min(int(parsed.get("count", count)), 20)

    logger.info(
        "Parsed query → location='%s' category='%s' maps_query='%s' count=%d",
        location, category, maps_query, count,
    )

    # Step 2 — Maps search
    raw = _maps_search(maps_query, count)

    # Step 3 — Fallback
    if len(raw) < 3:
        logger.info("Maps gave %d results, trying fallback", len(raw))
        fallback = _local_search_fallback(maps_query, count)
        # Merge, deduplicate by name
        existing_names = {r.get("title", "") for r in raw}
        for item in fallback:
            if item.get("title", "") not in existing_names:
                raw.append(item)
                existing_names.add(item.get("title", ""))

    # Step 4 — Normalise
    results = [_normalise(p) for p in raw if p.get("title")]

    return {
        "query":    user_query,
        "location": location,
        "category": category,
        "results":  results[:count],
        "error":    "" if results else "no_results",
    }
