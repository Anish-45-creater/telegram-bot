"""
main.py — Flask app. Handles webhook, location, admin dashboard, set_webhook.
"""
import logging
from datetime import datetime
from functools import wraps
import requests
from flask import Flask, request, jsonify, render_template_string, redirect, session, abort

from config.settings     import settings
from app.models.database import init_db, SessionLocal, User, Conversation, Search, AgentLog
from app.telegram.client import send_telegram_message, parse_incoming_update
from app.agent.orchestrator import AgentOrchestrator

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = settings.SECRET_KEY
init_db()

# ─── Auth ─────────────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated

# ─── Health ───────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status":"ok","time":datetime.utcnow().isoformat()})

# ─── Webhook ──────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    payload  = request.get_json(force=True, silent=True) or {}
    incoming = parse_incoming_update(payload)
    for msg in incoming:
        chat_id = msg["chat_id"]
        text    = msg["text"]
        name    = msg["name"]
        lat     = msg.get("lat")
        lng     = msg.get("lng")
        if not text: continue
        db = SessionLocal()
        try:
            orch  = AgentOrchestrator(db)
            reply = orch.process_message(str(chat_id), text, name, lat=lat, lng=lng)
            send_telegram_message(chat_id, reply)
        except Exception as e:
            logger.exception("Webhook error: %s", e)
            send_telegram_message(chat_id, "⚠️ Something went wrong. Please try again.")
        finally:
            db.close()
    return jsonify({"ok":True}), 200

# ─── Set webhook ──────────────────────────────────────────────────────────────
@app.route("/set_webhook", methods=["POST"])
def set_webhook():
    data = request.get_json(force=True, silent=True) or {}
    url  = data.get("url")
    if not url: return jsonify({"error":"url required"}), 400
    r = requests.post(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook",
        json={"url": url, "allowed_updates":["message"],"drop_pending_updates":True},
        timeout=10)
    return jsonify(r.json()), r.status_code

# ─── Admin CSS ────────────────────────────────────────────────────────────────
STYLE = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f6f9;color:#1a1a2e}
nav{background:#1a1a2e;color:#fff;padding:14px 24px;display:flex;align-items:center;gap:20px;position:sticky;top:0;z-index:100}
nav .brand{font-size:17px;font-weight:700;margin-right:auto}
nav a{color:#fff;text-decoration:none;font-size:14px;opacity:.75;padding:6px 12px;border-radius:6px}
nav a:hover,nav a.active{opacity:1;background:rgba(255,255,255,0.12)}
.container{max-width:1200px;margin:28px auto;padding:0 20px}
.stat-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:24px}
.stat{background:#fff;border-radius:12px;padding:22px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);text-align:center}
.stat .num{font-size:36px;font-weight:700;color:#1a1a2e}
.stat .lbl{font-size:13px;color:#6c757d;margin-top:4px}
.card{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.06);padding:24px;margin-bottom:20px}
h2{font-size:18px;margin-bottom:16px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f8f9fa;padding:10px 12px;text-align:left;font-weight:600;color:#495057;border-bottom:2px solid #e9ecef}
td{padding:9px 12px;border-bottom:1px solid #f1f3f5;vertical-align:top;word-break:break-word;max-width:300px}
tr:hover td{background:#f8f9ff}
.badge{display:inline-block;padding:2px 9px;border-radius:12px;font-size:11px;font-weight:600}
.green{background:#d1f7ee;color:#0a6847}.red{background:#fde8e8;color:#8b1a1a}
.blue{background:#dbeafe;color:#1e40af}.amber{background:#fef3c7;color:#92400e}
input[type=password],input[type=text]{border:1px solid #dee2e6;border-radius:8px;padding:9px 14px;font-size:14px;width:100%;margin-bottom:12px}
.btn{background:#1a1a2e;color:#fff;border:none;padding:10px 22px;border-radius:8px;cursor:pointer;font-size:14px}
</style>"""

# ─── Admin login ──────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    err = ""
    if request.method == "POST":
        if request.form.get("password","") == settings.SECRET_KEY[:16]:
            session["admin_logged_in"] = True; return redirect("/admin")
        err = "Invalid password."
    return render_template_string(f"""{STYLE}
<div style="max-width:380px;margin:80px auto">
<div class="card"><h2 style="margin-bottom:20px">🤖 Admin Login</h2>
<form method="POST">
<input type="password" name="password" placeholder="Password" autofocus>
<p style="color:red;font-size:13px;margin-bottom:10px">{err}</p>
<button class="btn">Login</button></form>
<p style="font-size:11px;color:#aaa;margin-top:12px">Password = first 16 chars of SECRET_KEY</p>
</div></div>""")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in",None); return redirect("/admin/login")

# ─── Admin dashboard ──────────────────────────────────────────────────────────
@app.route("/admin")
@app.route("/")
@admin_required
def admin_home():
    db = SessionLocal()
    try:
        uc = db.query(User).count()
        sc = db.query(Search).count()
        cc = db.query(Conversation).count()
        recent = db.query(Search).order_by(Search.created_at.desc()).limit(10).all()
        from sqlalchemy import func
        intents = db.query(Search.intent, func.count(Search.id).label("c"))\
                    .group_by(Search.intent).order_by(func.count(Search.id).desc()).limit(5).all()
    finally: db.close()
    irows = "".join(f"<tr><td>{i.intent}</td><td><b>{i.c}</b></td></tr>" for i in intents)
    srows = "".join(f"""<tr><td>{s.id}</td><td style="max-width:200px">{s.query[:60]}</td>
        <td><span class="badge blue">{s.intent}</span></td><td>{s.tool_used}</td>
        <td>{s.results_count}</td><td>{f"{s.execution_ms:.0f}ms" if s.execution_ms else "-"}</td>
        <td>{s.created_at.strftime("%d %b %H:%M") if s.created_at else ""}</td></tr>""" for s in recent)
    return render_template_string(f"""{STYLE}
<nav><span class="brand">🤖 Telegram AI Agent</span>
<a href="/admin" class="active">Dashboard</a><a href="/admin/users">Users</a>
<a href="/admin/searches">Searches</a><a href="/admin/chats">Chats</a>
<a href="/admin/logs">Logs</a><a href="/admin/logout">Logout</a></nav>
<div class="container">
<div class="stat-row">
<div class="stat"><div class="num">{uc}</div><div class="lbl">Total Users</div></div>
<div class="stat"><div class="num">{sc}</div><div class="lbl">Total Searches</div></div>
<div class="stat"><div class="num">{cc}</div><div class="lbl">Messages</div></div>
</div>
<div style="display:grid;grid-template-columns:1fr 2fr;gap:20px">
<div class="card"><h2>Top Intents</h2><table><thead><tr><th>Intent</th><th>Count</th></tr></thead>
<tbody>{irows}</tbody></table></div>
<div class="card"><h2>Recent Searches</h2><table>
<thead><tr><th>#</th><th>Query</th><th>Intent</th><th>Tool</th><th>Results</th><th>Time</th><th>Date</th></tr></thead>
<tbody>{srows}</tbody></table></div></div></div>""")

@app.route("/admin/users")
@admin_required
def admin_users():
    db = SessionLocal()
    try: users = db.query(User).order_by(User.last_seen.desc()).limit(100).all()
    finally: db.close()
    rows = "".join(f"""<tr><td>{u.id}</td><td><b>{u.phone}</b></td><td>{u.name or "-"}</td>
        <td>{u.request_count_day}</td>
        <td><span class="badge {'red' if u.is_blocked else 'green'}">{'Blocked' if u.is_blocked else 'Active'}</span></td>
        <td>{u.created_at.strftime("%d %b %Y") if u.created_at else ""}</td>
        <td>{u.last_seen.strftime("%d %b %H:%M") if u.last_seen else ""}</td></tr>""" for u in users)
    return render_template_string(f"""{STYLE}
<nav><span class="brand">🤖 Telegram AI Agent</span>
<a href="/admin">Dashboard</a><a href="/admin/users" class="active">Users</a>
<a href="/admin/searches">Searches</a><a href="/admin/chats">Chats</a>
<a href="/admin/logs">Logs</a><a href="/admin/logout">Logout</a></nav>
<div class="container"><div class="card"><h2>Users ({len(users)})</h2>
<table><thead><tr><th>#</th><th>Chat ID</th><th>Name</th><th>Daily Requests</th>
<th>Status</th><th>Joined</th><th>Last Seen</th></tr></thead>
<tbody>{rows}</tbody></table></div></div>""")

@app.route("/admin/searches")
@admin_required
def admin_searches():
    db = SessionLocal()
    try: searches = db.query(Search).order_by(Search.created_at.desc()).limit(200).all()
    finally: db.close()
    rows = "".join(f"""<tr><td>{s.id}</td><td>{s.user_id}</td>
        <td style="max-width:200px">{s.query[:70]}</td>
        <td><span class="badge blue">{s.intent}</span></td><td>{s.tool_used}</td>
        <td>{s.results_count}</td><td>{f"{s.execution_ms:.0f}ms" if s.execution_ms else "-"}</td>
        <td>{s.created_at.strftime("%d %b %H:%M") if s.created_at else ""}</td></tr>""" for s in searches)
    return render_template_string(f"""{STYLE}
<nav><span class="brand">🤖 Telegram AI Agent</span>
<a href="/admin">Dashboard</a><a href="/admin/users">Users</a>
<a href="/admin/searches" class="active">Searches</a><a href="/admin/chats">Chats</a>
<a href="/admin/logs">Logs</a><a href="/admin/logout">Logout</a></nav>
<div class="container"><div class="card"><h2>All Searches ({len(searches)})</h2>
<table><thead><tr><th>#</th><th>User</th><th>Query</th><th>Intent</th><th>Tool</th>
<th>Results</th><th>Time</th><th>Date</th></tr></thead>
<tbody>{rows}</tbody></table></div></div>""")

@app.route("/admin/chats")
@admin_required
def admin_chats():
    db = SessionLocal()
    try: convs = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(200).all()
    finally: db.close()
    rows = "".join(f"""<tr><td>{c.id}</td><td>{c.user_id}</td>
        <td><span class="badge {'green' if c.role=='assistant' else 'amber'}">{c.role}</span></td>
        <td style="max-width:400px">{c.content[:200]}</td>
        <td>{c.created_at.strftime("%d %b %H:%M") if c.created_at else ""}</td></tr>""" for c in convs)
    return render_template_string(f"""{STYLE}
<nav><span class="brand">🤖 Telegram AI Agent</span>
<a href="/admin">Dashboard</a><a href="/admin/users">Users</a>
<a href="/admin/searches">Searches</a><a href="/admin/chats" class="active">Chats</a>
<a href="/admin/logs">Logs</a><a href="/admin/logout">Logout</a></nav>
<div class="container"><div class="card"><h2>Chats ({len(convs)})</h2>
<table><thead><tr><th>#</th><th>User</th><th>Role</th><th>Message</th><th>Time</th></tr></thead>
<tbody>{rows}</tbody></table></div></div>""")

@app.route("/admin/logs")
@admin_required
def admin_logs():
    db = SessionLocal()
    try: logs = db.query(AgentLog).order_by(AgentLog.created_at.desc()).limit(300).all()
    finally: db.close()
    rows = "".join(f"""<tr><td>{lg.id}</td><td>{lg.search_id}</td><td><b>{lg.step}</b></td>
        <td>{lg.detail[:120] if lg.detail else ""}</td>
        <td><span class="badge {'green' if lg.status=='ok' else 'red'}">{lg.status}</span></td>
        <td>{lg.created_at.strftime("%H:%M:%S") if lg.created_at else ""}</td></tr>""" for lg in logs)
    return render_template_string(f"""{STYLE}
<nav><span class="brand">🤖 Telegram AI Agent</span>
<a href="/admin">Dashboard</a><a href="/admin/users">Users</a>
<a href="/admin/searches">Searches</a><a href="/admin/chats">Chats</a>
<a href="/admin/logs" class="active">Logs</a><a href="/admin/logout">Logout</a></nav>
<div class="container"><div class="card"><h2>Agent Logs ({len(logs)})</h2>
<table><thead><tr><th>#</th><th>Search</th><th>Step</th><th>Detail</th><th>Status</th><th>Time</th></tr></thead>
<tbody>{rows}</tbody></table></div></div>""")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.PORT, debug=settings.DEBUG)
