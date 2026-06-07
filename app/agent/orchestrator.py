"""
app/agent/orchestrator.py — Simplified orchestrator for AI-powered business discovery.

Pipeline:
  1. User management + rate limiting
  2. Greeting / special command handling
  3. AI search (Gemini + Google Search grounding)
  4. Format response
  5. Save to DB
"""
import time
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.agent.searcher import search_businesses
from app.agent.responder import format_business_results, format_error
from app.models.database import User, Conversation, Search, AgentLog
from config.settings import settings

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "👋 Welcome to the AI Business Discovery Bot!\n\n"
    "I find real businesses, services & professionals with:\n"
    "📞 Phone numbers\n"
    "📍 Addresses\n"
    "⭐ Ratings\n"
    "🌐 Websites\n\n"
    "Try asking:\n"
    "• Top 10 plumbers in Chennai with phone number\n"
    "• Best electricians in Bangalore\n"
    "• Top wedding photographers in Mumbai\n"
    "• Best hospitals in Coimbatore\n"
    "• Top lawyers in Chennai\n"
    "• Best restaurants in Delhi\n"
    "• Top CA firms in Chennai\n\n"
    "Just type your query!"
)


class AgentOrchestrator:
    def __init__(self, db: Session):
        self.db = db

    # ─── User management ──────────────────────────────────────────────────────

    def _get_or_create_user(self, phone: str, name: str | None = None) -> User:
        user = self.db.query(User).filter(User.phone == phone).first()
        if not user:
            user = User(phone=phone, name=name)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            logger.info("New user: %s", phone)
        else:
            user.last_seen = datetime.utcnow()
            if name and not user.name:
                user.name = name
            self.db.commit()
        return user

    def _check_rate_limit(self, user: User) -> bool:
        now = datetime.utcnow()
        if not user.last_request_hour or now - user.last_request_hour > timedelta(hours=1):
            user.request_count_hour = 0
            user.last_request_hour = now
        if user.request_count_hour >= settings.MAX_REQUESTS_PER_USER_PER_HOUR:
            return False
        user.request_count_hour += 1
        user.request_count_day += 1
        self.db.commit()
        return True

    def _save_turn(self, user_id: int, role: str, content: str, intent: str | None = None):
        turn = Conversation(user_id=user_id, role=role, content=content[:2000], intent=intent)
        self.db.add(turn)
        self.db.commit()

    def _log_step(self, search_id: int, step: str, detail: str, status: str = "ok"):
        log = AgentLog(search_id=search_id, step=step, detail=detail[:500], status=status)
        self.db.add(log)
        self.db.commit()

    # ─── Main entry point ─────────────────────────────────────────────────────

    def process_message(self, phone: str, message_text: str, name: str | None = None) -> str:
        t_start = time.time()

        # Step 0 — User & rate limit
        user = self._get_or_create_user(phone, name)

        if user.is_blocked:
            return "⛔ Your account has been blocked. Contact support."

        if not self._check_rate_limit(user):
            return (
                f"⚠️ Rate limit reached.\n\n"
                f"You've sent more than {settings.MAX_REQUESTS_PER_USER_PER_HOUR} "
                f"messages this hour. Please wait a bit."
            )

        self._save_turn(user.id, "user", message_text)

        # Step 1 — Handle greetings
        lower = message_text.lower().strip()
        if lower in {"hi", "hello", "hey", "start", "/start", "help", "/help"}:
            self._save_turn(user.id, "assistant", WELCOME_MESSAGE)
            return WELCOME_MESSAGE

        # Step 2 — Parse how many results user wants
        count = 10
        text_lower = message_text.lower()
        import re
        m = re.search(r"top\s+(\d+)|(\d+)\s+result", text_lower)
        if m:
            count = int(m.group(1) or m.group(2))
            count = min(count, 20)  # cap at 20

        # Step 3 — Create Search record
        search_rec = Search(
            user_id=user.id,
            query=message_text,
            intent="BUSINESS_SEARCH",
            tool_used="serpapi_maps",
        )
        self.db.add(search_rec)
        self.db.commit()
        self.db.refresh(search_rec)

        # Step 4 — AI business search
        self._log_step(search_rec.id, "search_start", f"Query: {message_text[:100]}")
        try:
            data = search_businesses(message_text, count=count)
        except Exception as exc:
            logger.exception("Search failed: %s", exc)
            data = {"results": [], "error": str(exc)}

        results = data.get("results", [])
        self._log_step(
            search_rec.id, "search_done",
            f"Found {len(results)} results | error={data.get('error', 'none')}"
        )

        # Step 5 — Format response
        if data.get("error") and not results:
            reply = format_error(message_text, data.get("error", "unknown"))
        else:
            reply = format_business_results(message_text, data)

        # Step 6 — Save metrics
        elapsed = (time.time() - t_start) * 1000
        search_rec.results_count = len(results)
        search_rec.results_json = results
        search_rec.response_text = reply[:2000]
        search_rec.execution_ms = elapsed
        self.db.commit()

        self._save_turn(user.id, "assistant", reply[:2000], intent="BUSINESS_SEARCH")

        logger.info(
            "Processed for %s in %.0fms — results=%d",
            phone, elapsed, len(results)
        )
        return reply
