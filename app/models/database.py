"""
app/models/database.py — SQLAlchemy ORM models.

Tables:
  users           — WhatsApp users
  conversations   — per-user conversation turns (memory)
  searches        — every search query with intent + result
  agent_logs      — step-by-step agent execution trace
"""
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from config.settings import settings

Base = declarative_base()


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_blocked = Column(Boolean, default=False)
    request_count_hour = Column(Integer, default=0)
    request_count_day = Column(Integer, default=0)
    last_request_hour = Column(DateTime, nullable=True)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    searches = relationship("Search", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)          # "user" | "assistant"
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")


class Search(Base):
    __tablename__ = "searches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    query = Column(Text, nullable=False)
    intent = Column(String(50), nullable=False)
    tool_used = Column(String(50), nullable=False)
    results_count = Column(Integer, default=0)
    results_json = Column(JSON, nullable=True)         # cleaned result list
    response_text = Column(Text, nullable=True)
    execution_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="searches")
    agent_logs = relationship("AgentLog", back_populates="search", cascade="all, delete-orphan")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("searches.id"), nullable=False)
    step = Column(String(50), nullable=False)          # e.g. "intent_detection"
    detail = Column(Text, nullable=True)
    status = Column(String(20), default="ok")          # "ok" | "error"
    created_at = Column(DateTime, default=datetime.utcnow)

    search = relationship("Search", back_populates="agent_logs")


# ─────────────────────────────────────────────────────────────────────────────
# Engine / session factory
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_db_url(url: str) -> str:
    """
    Supabase (and some other providers) hand out URLs starting with
    'postgres://'. SQLAlchemy 1.4+/2.x requires the 'postgresql://' scheme
    with psycopg2, so rewrite it if needed.
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


_DB_URL = _normalize_db_url(settings.DATABASE_URL)
_is_sqlite = _DB_URL.startswith("sqlite")
_is_postgres = _DB_URL.startswith("postgresql")

_connect_args = {}
if _is_sqlite:
    _connect_args = {"check_same_thread": False}
elif _is_postgres:
    # Supabase requires SSL, and Supabase's pooled connection (pgbouncer,
    # port 6543) can silently drop idle connections — sslmode + pool_pre_ping
    # + pool_recycle keep long-lived workers from erroring on a stale conn.
    _connect_args = {"sslmode": "require"}

_engine_kwargs = {"connect_args": _connect_args, "echo": False}
if _is_postgres:
    _engine_kwargs.update(
        pool_pre_ping=True,   # test connection before using it
        pool_recycle=300,     # recycle every 5 min, well under pgbouncer/Supabase idle timeout
    )

engine = create_engine(_DB_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Dependency-injectable DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
