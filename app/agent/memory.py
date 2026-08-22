"""
app/agent/memory.py — Per-user conversation memory.
Stores last 10 turns per user in DB so the bot remembers context.
e.g. User says "show more" after a search — bot knows what to search more of.
"""
import logging
from sqlalchemy.orm import Session
from app.models.database import Conversation

logger = logging.getLogger(__name__)
MAX_MEMORY_TURNS = 10


def get_memory(db: Session, user_id: int) -> list[dict]:
    """Return last N conversation turns as list of {role, content}."""
    turns = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(MAX_MEMORY_TURNS)
        .all()
    )
    turns.reverse()
    return [{"role": t.role, "content": t.content, "intent": t.intent} for t in turns]


def save_turn(db: Session, user_id: int, role: str, content: str, intent: str = None):
    turn = Conversation(user_id=user_id, role=role, content=content[:2000], intent=intent)
    db.add(turn)
    db.commit()


def get_last_search(db: Session, user_id: int) -> str | None:
    """Get the most recent user search query (for 'show more' / 'similar' requests)."""
    last = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.role == "user")
        .order_by(Conversation.created_at.desc())
        .offset(1)   # skip current message
        .first()
    )
    return last.content if last else None
