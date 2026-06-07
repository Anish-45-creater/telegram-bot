"""
main.py — Flask application entry point (Telegram edition).

Routes:
  POST /webhook        — Incoming Telegram Updates
  GET  /               — Admin dashboard home
  GET  /admin/users    — User management
  GET  /admin/chats    — Conversation history
  GET  /admin/searches — Search analytics
  GET  /admin/logs     — Agent execution logs
  GET  /health         — Health check for hosting platforms
  POST /set_webhook    — Register Telegram webhook (call once after deploy)
"""
import hashlib
import hmac
import logging
from datetime import datetime
from functools import wraps

import requests
from flask import Flask, request, jsonify, render_template_string, abort, redirect, session

from config.settings import settings
from app.models.database import init_db, SessionLocal, User, Conversation, Search, AgentLog
from app.telegram.client import send_telegram_message, parse_incoming_update
from app.agent.orchestrator import AgentOrchestrator

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = settings.SECRET_KEY

init_db()
logger.info("Database initialised.")


# ─── Admin auth decorator ─────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated


# ─── Health check ─────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ─── Telegram Webhook ─────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook_receive():
    """Receive incoming Telegram Update objects."""

    # Optional: verify Telegram's secret_token header
    if settings.TELEGRAM_WEBHOOK_SECRET:
        sent = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(sent, settings.TELEGRAM_WEBHOOK_SECRET):
            logger.warning("Webhook secret mismatch — ignoring update.")
            abort(403)

    payload = request.get_json(force=True, silent=True) or {}
    incoming = parse_incoming_update(payload)

    for msg in incoming:
        chat_id = msg["chat_id"]
        text = msg["text"]
        name = msg["name"]

        if not text:
            continue

        logger.info("Incoming from %s (%s): %.80s", chat_id, name, text)

        db = SessionLocal()
        try:
            orchestrator = AgentOrchestrator(db)
            reply = orchestrator.process_message(str(chat_id), text, name)
            send_telegram_message(chat_id, reply)
        except Exception as exc:
            logger.exception("Processing failed for %s: %s", chat_id, exc)
            send_telegram_message(chat_id, "Sorry, something went wrong. Please try again in a moment.")
        finally:
            db.close()

    return jsonify({"status": "received"}), 200


# ─── Register Telegram Webhook ────────────────────────────────────────────────

@app.route("/set_webhook", methods=["POST"])
def set_webhook():
    """
    Register this server's URL with Telegram as the webhook endpoint.
    Call once after deploy:
        curl -X POST https://your-app.onrender.com/set_webhook \
             -H "Content-Type: application/json" \
             -d '{"url": "https://your-app.onrender.com/webhook"}'
    """
    data = request.get_json(force=True, silent=True) or {}
    webhook_url = data.get("url")
    if not webhook_url:
        return jsonify({"error": "url field required"}), 400

    params: dict = {
        "url": webhook_url,
        "allowed_updates": ["message"],
        "drop_pending_updates": True,
    }
    if settings.TELEGRAM_WEBHOOK_SECRET:
        params["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET

    token = settings.TELEGRAM_BOT_TOKEN
    r = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json=params,
        timeout=10,
    )
    return jsonify(r.json()), r.status_code


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

ADMIN_STYLE = """
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f9fa;color:#212529}
  nav{background:#2b5278;color:#fff;padding:12px 24px;display:flex;align-items:center;gap:20px}
  nav a{color:#fff;text-decoration:none;font-size:14px;opacity:.85}
  nav a:hover,nav a.active{opacity:1;font-weight:600}
  nav .brand{font-size:17px;font-weight:700;margin-right:auto}
  .container{max-width:1100px;margin:28px auto;padding:0 20px}
  .card{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:24px;margin-bottom:20px}
  .stat-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:16px;margin-bottom:24px}
  .stat{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);text-align:center}
  .stat .num{font-size:32px;font-weight:700;color:#2b5278}
  .stat .lbl{font-size:13px;color:#6c757d;margin-top:4px}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th{background:#f1f3f5;padding:10px 12px;text-align:left;font-weight:600;color:#495057}
  td{padding:9px 12px;border-bottom:1px solid #f1f3f5;vertical-align:top;word-break:break-word}
  tr:hover td{background:#f0f4ff}
  .badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600}
  .badge-green{background:#d1f7ee;color:#0a6847}
  .badge-red{background:#fde8e8;color:#8b1a1a}
  .badge-blue{background:#dbeafe;color:#1e40af}
  .badge-amber{background:#fef3c7;color:#92400e}
  h2{font-size:20px;margin-bottom:16px;color:#212529}
  input[type=submit],button{background:#2b5278;color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-size:14px}
  input[type=text],input[type=password]{border:1px solid #ced4da;border-radius:6px;padding:8px 12px;font-size:14px;width:100%;margin-bottom:12px}
</style>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == settings.SECRET_KEY[:16]:
            session["admin_logged_in"] = True
            return redirect("/admin")
        error = "Invalid password."
    return render_template_string(f"""
    {ADMIN_STYLE}
    <div style="max-width:360px;margin:80px auto">
      <div class="card">
        <h2 style="margin-bottom:20px">🤖 Telegram Agent Admin</h2>
        <form method="POST">
          <input type="password" name="password" placeholder="Admin password" autofocus>
          <p style="color:red;font-size:13px;margin-bottom:8px">{error}</p>
          <input type="submit" value="Login">
        </form>
        <p style="font-size:12px;color:#aaa;margin-top:12px">Password = first 16 chars of SECRET_KEY</p>
      </div>
    </div>""")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin/login")


@app.route("/admin")
@app.route("/")
@admin_required
def admin_home():
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        search_count = db.query(Search).count()
        conv_count = db.query(Conversation).count()
        recent_searches = db.query(Search).order_by(Search.created_at.desc()).limit(8).all()
        from sqlalchemy import func
        top_intents = (
            db.query(Search.intent, func.count(Search.id).label("cnt"))
            .group_by(Search.intent)
            .order_by(func.count(Search.id).desc())
            .limit(5)
            .all()
        )
    finally:
        db.close()

    intent_html = "".join(
        f"<tr><td>{i.intent}</td><td><b>{i.cnt}</b></td></tr>" for i in top_intents
    )
    search_rows = "".join(f"""
      <tr>
        <td>{s.id}</td>
        <td>{s.query[:60]}</td>
        <td><span class="badge badge-blue">{s.intent}</span></td>
        <td>{s.tool_used}</td>
        <td>{s.results_count}</td>
        <td>{f"{s.execution_ms:.0f}ms" if s.execution_ms else "-"}</td>
        <td>{s.created_at.strftime("%d %b %H:%M") if s.created_at else ""}</td>
      </tr>""" for s in recent_searches)

    return render_template_string(f"""
    {ADMIN_STYLE}
    <nav>
      <span class="brand">🤖 Telegram AI Agent</span>
      <a href="/admin" class="active">Dashboard</a>
      <a href="/admin/users">Users</a>
      <a href="/admin/searches">Searches</a>
      <a href="/admin/chats">Chats</a>
      <a href="/admin/logs">Logs</a>
      <a href="/admin/logout">Logout</a>
    </nav>
    <div class="container">
      <div class="stat-row">
        <div class="stat"><div class="num">{user_count}</div><div class="lbl">Total Users</div></div>
        <div class="stat"><div class="num">{search_count}</div><div class="lbl">Searches</div></div>
        <div class="stat"><div class="num">{conv_count}</div><div class="lbl">Messages</div></div>
      </div>
      <div class="card">
        <h2>Top Intents</h2>
        <table><thead><tr><th>Intent</th><th>Count</th></tr></thead>
        <tbody>{intent_html}</tbody></table>
      </div>
      <div class="card">
        <h2>Recent Searches</h2>
        <table><thead><tr><th>#</th><th>Query</th><th>Intent</th><th>Tool</th><th>Results</th><th>Time</th><th>Date</th></tr></thead>
        <tbody>{search_rows}</tbody></table>
      </div>
    </div>""")


@app.route("/admin/users")
@admin_required
def admin_users():
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.last_seen.desc()).limit(100).all()
    finally:
        db.close()

    rows = "".join(f"""
      <tr>
        <td>{u.id}</td>
        <td><b>{u.phone}</b></td>
        <td>{u.name or "-"}</td>
        <td>{u.request_count_day}</td>
        <td><span class="badge {'badge-red' if u.is_blocked else 'badge-green'}">{'Blocked' if u.is_blocked else 'Active'}</span></td>
        <td>{u.created_at.strftime("%d %b %Y") if u.created_at else ""}</td>
        <td>{u.last_seen.strftime("%d %b %H:%M") if u.last_seen else ""}</td>
      </tr>""" for u in users)

    return render_template_string(f"""
    {ADMIN_STYLE}
    <nav>
      <span class="brand">🤖 Telegram AI Agent</span>
      <a href="/admin">Dashboard</a>
      <a href="/admin/users" class="active">Users</a>
      <a href="/admin/searches">Searches</a>
      <a href="/admin/chats">Chats</a>
      <a href="/admin/logs">Logs</a>
      <a href="/admin/logout">Logout</a>
    </nav>
    <div class="container">
      <div class="card">
        <h2>Users ({len(users)})</h2>
        <table><thead><tr><th>#</th><th>Chat ID</th><th>Name</th><th>Daily Requests</th><th>Status</th><th>Joined</th><th>Last Seen</th></tr></thead>
        <tbody>{rows}</tbody></table>
      </div>
    </div>""")


@app.route("/admin/searches")
@admin_required
def admin_searches():
    db = SessionLocal()
    try:
        searches = db.query(Search).order_by(Search.created_at.desc()).limit(200).all()
    finally:
        db.close()

    rows = "".join(f"""
      <tr>
        <td>{s.id}</td>
        <td>{s.user_id}</td>
        <td>{s.query[:70]}</td>
        <td><span class="badge badge-blue">{s.intent}</span></td>
        <td>{s.tool_used}</td>
        <td>{s.results_count}</td>
        <td>{f"{s.execution_ms:.0f}ms" if s.execution_ms else "-"}</td>
        <td>{s.created_at.strftime("%d %b %H:%M") if s.created_at else ""}</td>
      </tr>""" for s in searches)

    return render_template_string(f"""
    {ADMIN_STYLE}
    <nav>
      <span class="brand">🤖 Telegram AI Agent</span>
      <a href="/admin">Dashboard</a>
      <a href="/admin/users">Users</a>
      <a href="/admin/searches" class="active">Searches</a>
      <a href="/admin/chats">Chats</a>
      <a href="/admin/logs">Logs</a>
      <a href="/admin/logout">Logout</a>
    </nav>
    <div class="container">
      <div class="card">
        <h2>All Searches ({len(searches)})</h2>
        <table><thead><tr><th>#</th><th>User</th><th>Query</th><th>Intent</th><th>Tool</th><th>Results</th><th>Time</th><th>Date</th></tr></thead>
        <tbody>{rows}</tbody></table>
      </div>
    </div>""")


@app.route("/admin/chats")
@admin_required
def admin_chats():
    db = SessionLocal()
    try:
        convs = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(200).all()
    finally:
        db.close()

    rows = "".join(f"""
      <tr>
        <td>{c.id}</td>
        <td>{c.user_id}</td>
        <td><span class="badge {'badge-green' if c.role=='assistant' else 'badge-amber'}">{c.role}</span></td>
        <td style="max-width:400px">{c.content[:200]}</td>
        <td>{c.created_at.strftime("%d %b %H:%M") if c.created_at else ""}</td>
      </tr>""" for c in convs)

    return render_template_string(f"""
    {ADMIN_STYLE}
    <nav>
      <span class="brand">🤖 Telegram AI Agent</span>
      <a href="/admin">Dashboard</a>
      <a href="/admin/users">Users</a>
      <a href="/admin/searches">Searches</a>
      <a href="/admin/chats" class="active">Chats</a>
      <a href="/admin/logs">Logs</a>
      <a href="/admin/logout">Logout</a>
    </nav>
    <div class="container">
      <div class="card">
        <h2>Conversation History ({len(convs)})</h2>
        <table><thead><tr><th>#</th><th>User</th><th>Role</th><th>Message</th><th>Time</th></tr></thead>
        <tbody>{rows}</tbody></table>
      </div>
    </div>""")


@app.route("/admin/logs")
@admin_required
def admin_logs():
    db = SessionLocal()
    try:
        logs = db.query(AgentLog).order_by(AgentLog.created_at.desc()).limit(300).all()
    finally:
        db.close()

    rows = "".join(f"""
      <tr>
        <td>{lg.id}</td>
        <td>{lg.search_id}</td>
        <td><b>{lg.step}</b></td>
        <td>{lg.detail[:120] if lg.detail else ""}</td>
        <td><span class="badge {'badge-green' if lg.status=='ok' else 'badge-red'}">{lg.status}</span></td>
        <td>{lg.created_at.strftime("%H:%M:%S") if lg.created_at else ""}</td>
      </tr>""" for lg in logs)

    return render_template_string(f"""
    {ADMIN_STYLE}
    <nav>
      <span class="brand">🤖 Telegram AI Agent</span>
      <a href="/admin">Dashboard</a>
      <a href="/admin/users">Users</a>
      <a href="/admin/searches">Searches</a>
      <a href="/admin/chats">Chats</a>
      <a href="/admin/logs" class="active">Logs</a>
      <a href="/admin/logout">Logout</a>
    </nav>
    <div class="container">
      <div class="card">
        <h2>Agent Execution Logs ({len(logs)})</h2>
        <table><thead><tr><th>#</th><th>Search ID</th><th>Step</th><th>Detail</th><th>Status</th><th>Time</th></tr></thead>
        <tbody>{rows}</tbody></table>
      </div>
    </div>""")


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.PORT, debug=settings.DEBUG)
