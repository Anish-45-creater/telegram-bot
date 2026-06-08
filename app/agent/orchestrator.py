"""
app/agent/orchestrator.py — Agentic orchestrator with GPS, memory, MCP tool routing.
"""
import re, time, logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.agent.searcher  import search_businesses
from app.agent.responder import format_business_results, format_error, format_nearby_results
from app.agent.memory    import get_memory, save_turn, get_last_search
from app.agent.mcp_tools import TOOL_REGISTRY, route_tool, tool_news_search, tool_web_search
from app.models.database import User, Conversation, Search, AgentLog
from app.telegram.client import send_location_request
from config.settings     import settings

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "👋 Welcome to the AI Business Discovery Bot!\n\n"
    "I find real businesses, services & professionals with:\n"
    "📞 Phone numbers  📍 Addresses  ⭐ Ratings  🌐 Websites\n\n"
    "Try asking:\n"
    "• Top 10 plumbers in Chennai\n"
    "• Best electricians in Bangalore\n"
    "• Top hospitals in Coimbatore\n"
    "• Top restaurants in Delhi\n"
    "• Hotels near me  ← share your location!\n"
    "• Latest news about startups\n\n"
    "📍 For 'near me' searches, just share your location when asked!\n"
    "Type your query to get started!"
)

HELP_MESSAGE = (
    "🤖 What I can do:\n\n"
    "🏢 BUSINESS SEARCH\n"
    "  Top 10 electricians in Chennai\n"
    "  Best plumbers in Bangalore\n"
    "  Top hospitals in Coimbatore\n\n"
    "📍 NEARBY SEARCH (GPS)\n"
    "  Hotels near me\n"
    "  Restaurants nearby\n"
    "  Pharmacies near my location\n\n"
    "📰 NEWS\n"
    "  Latest tech news\n"
    "  News about Chennai startups\n\n"
    "🔍 WEB SEARCH\n"
    "  How to apply for Aadhaar card\n"
    "  What is GST registration process\n\n"
    "🔁 CONTEXT\n"
    "  show more  ← repeats last search with more results\n"
    "  similar    ← searches related category"
)


class AgentOrchestrator:
    def __init__(self, db: Session):
        self.db = db

    # ── User management ───────────────────────────────────────────────────────

    def _get_or_create_user(self, phone: str, name: str = None) -> User:
        user = self.db.query(User).filter(User.phone == phone).first()
        if not user:
            user = User(phone=phone, name=name)
            self.db.add(user); self.db.commit(); self.db.refresh(user)
            logger.info("New user: %s", phone)
        else:
            user.last_seen = datetime.utcnow()
            if name and not user.name: user.name = name
            self.db.commit()
        return user

    def _rate_ok(self, user: User) -> bool:
        now = datetime.utcnow()
        if not user.last_request_hour or now - user.last_request_hour > timedelta(hours=1):
            user.request_count_hour = 0; user.last_request_hour = now
        if user.request_count_hour >= settings.MAX_REQUESTS_PER_USER_PER_HOUR:
            return False
        user.request_count_hour += 1; user.request_count_day += 1
        self.db.commit(); return True

    def _log(self, search_id, step, detail, status="ok"):
        self.db.add(AgentLog(search_id=search_id, step=step,
                             detail=str(detail)[:500], status=status))
        self.db.commit()

    def _save_search(self, user_id, query, intent, tool, results, reply, ms):
        s = Search(user_id=user_id, query=query, intent=intent, tool_used=tool,
                   results_count=len(results), results_json=results,
                   response_text=reply[:2000], execution_ms=ms)
        self.db.add(s); self.db.commit(); return s

    # ── Main entry point ──────────────────────────────────────────────────────

    def process_message(self, phone: str, message_text: str,
                        name: str = None,
                        lat: float = None, lng: float = None) -> str:
        t0   = time.time()
        user = self._get_or_create_user(phone, name)

        if user.is_blocked:
            return "⛔ Your account has been blocked. Contact support."
        if not self._rate_ok(user):
            return (f"⚠️ Rate limit: {settings.MAX_REQUESTS_PER_USER_PER_HOUR} "
                    f"requests/hour reached. Please wait.")

        save_turn(self.db, user.id, "user", message_text)

        lower = message_text.lower().strip()

        # ── Greetings ─────────────────────────────────────────────────────────
        if lower in {"hi","hello","hey","start","/start"}:
            save_turn(self.db, user.id, "assistant", WELCOME_MESSAGE)
            return WELCOME_MESSAGE

        if lower in {"help","/help","commands","/commands"}:
            save_turn(self.db, user.id, "assistant", HELP_MESSAGE)
            return HELP_MESSAGE

        # ── GPS Location shared ───────────────────────────────────────────────
        if message_text == "__location__" and lat and lng:
            # Ask what to search nearby
            prompt = f"📍 Got your location!\n\nWhat would you like to find nearby?\nReply with something like:\n• Hotels near me\n• Restaurants nearby\n• Hospitals near me\n• Pharmacies nearby"
            # Store coordinates in last conversation for next message
            save_turn(self.db, user.id, "assistant", prompt,
                      intent=f"GPS:{lat},{lng}")
            return prompt

        # ── "Near me" — check if we have a pending GPS ────────────────────────
        if any(t in lower for t in ["near me","nearby","near my","around me","closest"]):
            # Try to get GPS from previous turn
            memory = get_memory(self.db, user.id)
            gps_turn = next((m for m in reversed(memory)
                             if m["role"]=="assistant" and
                             (m.get("intent","") or "").startswith("GPS:")), None)
            if gps_turn:
                coords = gps_turn["intent"].replace("GPS:","").split(",")
                lat, lng = float(coords[0]), float(coords[1])
            else:
                # Ask user to share location
                send_location_request(phone)
                return "📍 Please share your location using the button below so I can find nearby places!"

        # ── "Show more" / "similar" — use memory ─────────────────────────────
        if lower in {"show more","more","similar","again"}:
            last = get_last_search(self.db, user.id)
            if last:
                message_text = last
                lower = message_text.lower()
            else:
                return "❓ No previous search found. Please type a new query."

        # ── Route to correct tool ─────────────────────────────────────────────
        count = 10
        m = re.search(r"top\s+(\d+)|(\d+)\s+result", lower)
        if m: count = min(int(m.group(1) or m.group(2)), 20)

        tool_name = route_tool(message_text)
        intent    = tool_name.upper()
        reply     = ""
        results   = []

        try:
            if tool_name == "nearby_search" and lat and lng:
                fn   = TOOL_REGISTRY["nearby_search"]["fn"]
                results = fn(message_text, lat, lng, count)
                data = {"query": message_text, "location": f"near you ({lat:.4f},{lng:.4f})",
                        "category": message_text, "results": results}
                reply = format_nearby_results(message_text, data)

            elif tool_name == "news_search":
                results = tool_news_search(message_text, count=8)
                lines = [f"📰 NEWS: {message_text}\n"]
                for i, r in enumerate(results, 1):
                    lines.append(f"{i}. {r['title']}")
                    if r.get("source"): lines.append(f"   📰 {r['source']}")
                    if r.get("date"):   lines.append(f"   📅 {r['date']}")
                    if r.get("link"):   lines.append(f"   🔗 {r['link']}")
                    lines.append("")
                reply = "\n".join(lines)

            elif tool_name == "web_search":
                results = tool_web_search(message_text, count=5)
                lines = [f"🔍 WEB: {message_text}\n"]
                for i, r in enumerate(results, 1):
                    lines.append(f"{i}. {r['title']}")
                    if r.get("snippet"): lines.append(f"   {r['snippet'][:120]}")
                    if r.get("link"):    lines.append(f"   🔗 {r['link']}")
                    lines.append("")
                reply = "\n".join(lines)

            else:  # business_search (default)
                data    = search_businesses(message_text, count=count, lat=lat, lng=lng)
                results = data.get("results", [])
                reply   = format_business_results(message_text, data) if results else \
                          format_error(message_text, "no_results")

        except Exception as exc:
            logger.exception("Tool %s failed: %s", tool_name, exc)
            reply = format_error(message_text, str(exc))

        elapsed = (time.time() - t0) * 1000
        self._save_search(user.id, message_text, intent, tool_name, results, reply, elapsed)
        save_turn(self.db, user.id, "assistant", reply[:2000], intent=intent)
        logger.info("Done %s in %.0fms results=%d", phone, elapsed, len(results))
        return reply
