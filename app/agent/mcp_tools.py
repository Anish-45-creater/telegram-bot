"""
app/agent/mcp_tools.py — MCP-style agentic tool registry.

This is an agentic framework: the orchestrator can call multiple tools
in sequence, pass results between them, and retry on failure.

Current tools (all free):
  - business_search   : SerpAPI Google Maps
  - nearby_search     : SerpAPI Maps with GPS coordinates
  - web_search        : SerpAPI organic search
  - news_search       : SerpAPI Google News
  - summarise         : Gemini free tier

To ADD a new tool: add a function below and register it in TOOL_REGISTRY.
The orchestrator will automatically discover and use it.
"""
import logging
import requests
from config.settings import settings

logger = logging.getLogger(__name__)
SERPAPI_BASE = "https://serpapi.com/search.json"


def _serpapi(params: dict) -> dict:
    params["api_key"] = settings.SERPAPI_KEY
    params.setdefault("hl", "en")
    params.setdefault("gl", "in")
    try:
        r = requests.get(SERPAPI_BASE, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("SerpAPI error: %s", e)
        return {}


# ─── Tool: Business Search ────────────────────────────────────────────────────
def tool_business_search(query: str, count: int = 10) -> list[dict]:
    data = _serpapi({"engine":"google_maps","q":query,"type":"search"})
    results = []
    for p in data.get("local_results",[])[:count]:
        phone = p.get("phone") or (p.get("extensions") or {}).get("phone","") or ""
        results.append({
            "name":    p.get("title",""),
            "phone":   phone,
            "address": p.get("address",""),
            "rating":  str(p.get("rating",""))  if p.get("rating")  else "",
            "reviews": str(p.get("reviews","")) if p.get("reviews") else "",
            "website": p.get("website",""),
            "type":    p.get("type",""),
        })
    return results


# ─── Tool: Nearby Search (GPS) ────────────────────────────────────────────────
def tool_nearby_search(query: str, lat: float, lng: float, count: int = 10) -> list[dict]:
    ll = f"@{lat},{lng},14z"
    data = _serpapi({"engine":"google_maps","q":query,"type":"search","ll":ll})
    results = []
    for p in data.get("local_results",[])[:count]:
        phone = p.get("phone") or (p.get("extensions") or {}).get("phone","") or ""
        results.append({
            "name":    p.get("title",""),
            "phone":   phone,
            "address": p.get("address",""),
            "rating":  str(p.get("rating",""))  if p.get("rating")  else "",
            "reviews": str(p.get("reviews","")) if p.get("reviews") else "",
            "website": p.get("website",""),
            "distance": p.get("distance",""),
        })
    return results


# ─── Tool: Web Search ─────────────────────────────────────────────────────────
def tool_web_search(query: str, count: int = 5) -> list[dict]:
    data = _serpapi({"engine":"google","q":query,"num":count})
    return [
        {"title":r.get("title",""),"link":r.get("link",""),"snippet":r.get("snippet","")}
        for r in data.get("organic_results",[])[:count]
    ]


# ─── Tool: News Search ────────────────────────────────────────────────────────
def tool_news_search(query: str, count: int = 5) -> list[dict]:
    data = _serpapi({"engine":"google_news","q":query})
    items = data.get("news_results") or data.get("organic_results",[])
    return [
        {"title":r.get("title",""),"link":r.get("link",""),
         "source":r.get("source",{}).get("name","") if isinstance(r.get("source"),dict) else "",
         "date":r.get("date","")}
        for r in items[:count]
    ]


# ─── Tool Registry (add new tools here) ──────────────────────────────────────
TOOL_REGISTRY = {
    "business_search": {
        "fn":          tool_business_search,
        "description": "Search businesses by name/category and city",
        "triggers":    ["top","best","find","search","near","electrician","plumber",
                        "hospital","hotel","restaurant","shop","lawyer","doctor",
                        "photographer","gym","school","college","bank","ca firm"],
    },
    "nearby_search": {
        "fn":          tool_nearby_search,
        "description": "Search businesses near GPS coordinates",
        "triggers":    ["near me","nearby","closest","around me","my location"],
    },
    "web_search": {
        "fn":          tool_web_search,
        "description": "General web search",
        "triggers":    ["how","what","why","when","which","tell me about"],
    },
    "news_search": {
        "fn":          tool_news_search,
        "description": "Latest news search",
        "triggers":    ["news","latest","today","current","recent"],
    },
}


def route_tool(message: str) -> str:
    """Pick the best tool based on message keywords."""
    lower = message.lower()
    # GPS / nearby always wins if location was shared
    if any(t in lower for t in TOOL_REGISTRY["nearby_search"]["triggers"]):
        return "nearby_search"
    if any(t in lower for t in TOOL_REGISTRY["news_search"]["triggers"]):
        return "news_search"
    if any(t in lower for t in TOOL_REGISTRY["business_search"]["triggers"]):
        return "business_search"
    return "web_search"
