"""
app/agent/searcher.py — SerpAPI Google Maps + Gemini (free tier, no grounding).
Supports both text queries and GPS coordinates.
"""
import json, logging, re, requests
from config.settings import settings

logger = logging.getLogger(__name__)
SERPAPI_BASE = "https://serpapi.com/search.json"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"


def _gemini(prompt: str, max_tokens: int = 300) -> str:
    if not settings.GEMINI_API_KEY:
        return ""
    try:
        r = requests.post(
            GEMINI_URL.format(key=settings.GEMINI_API_KEY),
            json={"contents":[{"role":"user","parts":[{"text":prompt}]}],
                  "generation_config":{"temperature":0,"max_output_tokens":max_tokens}},
            timeout=15)
        r.raise_for_status()
        raw = ""
        for part in r.json().get("candidates",[{}])[0].get("content",{}).get("parts",[]):
            raw += part.get("text","")
        return re.sub(r"```(?:json)?|```","",raw).strip()
    except Exception as e:
        logger.warning("Gemini error: %s", e)
        return ""


def _parse_query(user_query: str) -> dict:
    raw = _gemini(f"""Extract from this business search query. Return ONLY valid JSON.
Query: "{user_query}"
Return: {{"location":"city name or empty","category":"type of business","count":<number default 10 max 20>,"maps_query":"short optimised query for Google Maps"}}""")
    try:
        return json.loads(raw)
    except:
        m = re.search(r"\b(\d+)\b", user_query)
        return {"location":"","category":user_query,"count":int(m.group(1)) if m else 10,"maps_query":user_query}


def _maps_search(q: str, count: int, ll: str = None) -> list:
    if not settings.SERPAPI_KEY:
        return []
    params = {"engine":"google_maps","q":q,"type":"search","hl":"en","gl":"in","api_key":settings.SERPAPI_KEY}
    if ll:
        params["ll"] = ll  # e.g. "@12.9716,77.5946,14z"
    try:
        r = requests.get(SERPAPI_BASE, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("local_results",[])[:count]
    except Exception as e:
        logger.exception("SerpAPI Maps error: %s", e)
        return []


def _normalise(p: dict) -> dict:
    phone = p.get("phone") or (p.get("extensions") or {}).get("phone","") or ""
    return {
        "name":    p.get("title",""),
        "phone":   phone,
        "address": p.get("address",""),
        "rating":  str(p.get("rating",""))  if p.get("rating")  else "",
        "reviews": str(p.get("reviews","")) if p.get("reviews") else "",
        "website": p.get("website",""),
        "type":    p.get("type",""),
    }


def search_businesses(user_query: str, count: int = 10, lat: float = None, lng: float = None) -> dict:
    """
    Search businesses by text query OR GPS coordinates.
    lat/lng: passed when user shares their Telegram location.
    """
    parsed     = _parse_query(user_query)
    location   = parsed.get("location","")
    category   = parsed.get("category", user_query)
    maps_query = parsed.get("maps_query", user_query)
    count      = min(int(parsed.get("count", count)), 20)

    # GPS mode — use coordinates directly
    ll = None
    if lat is not None and lng is not None:
        ll = f"@{lat},{lng},14z"
        location = f"{lat:.4f}, {lng:.4f} (your location)"
        logger.info("GPS search: %s ll=%s", maps_query, ll)

    raw     = _maps_search(maps_query, count, ll=ll)
    results = [_normalise(p) for p in raw if p.get("title")]

    return {
        "query":    user_query,
        "location": location,
        "category": category,
        "results":  results[:count],
        "error":    "" if results else "no_results",
    }
