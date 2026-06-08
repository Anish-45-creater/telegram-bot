# 🤖 Telegram AI Search Agent

A production-ready AI search agent for Telegram, deployable to Render in minutes.
Users chat with the bot and get real-time search results — local businesses, hotels,
restaurants, hospitals, LinkedIn profiles, news, and more.

## Architecture

```
Telegram User
    │  (message)
    ▼
Flask /webhook  ──► AgentOrchestrator
                         │
                    ┌────┴────┐
                    │         │
               Intent      Tool Router
               (Gemini)   (SerpAPI)
                    │         │
                    └────┬────┘
                         │
                    Extraction
                    Engine
                         │
                    Responder
                    (Gemini)
                         │
                    send_telegram_message()
```

## Quick Start

### 1. Create your Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF...`)

### 2. Get API keys

| Key | Where |
|-----|-------|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/app/apikey) — free |
| `SERPAPI_KEY` | [serpapi.com](https://serpapi.com) — 100 free searches/month |

### 3. Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New → Blueprint**
3. Connect your repo — Render reads `render.yaml` automatically
4. Set the environment variables in the Render dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_WEBHOOK_SECRET` (any random string, e.g. `openssl rand -hex 32`)
   - `GEMINI_API_KEY`
   - `SERPAPI_KEY`
5. Deploy

### 4. Register the webhook

After your Render URL is live (e.g. `https://telegram-ai-agent.onrender.com`),
run this once to tell Telegram where to send updates:

```bash
curl -X POST https://telegram-ai-agent.onrender.com/set_webhook \
     -H "Content-Type: application/json" \
     -d '{"url": "https://telegram-ai-agent.onrender.com/webhook"}'
```

You should get `{"ok": true, "result": true, ...}` back.

### 5. Test

Open your bot on Telegram and send `hi`.

---

## Local Development

```bash
cp .env.example .env
# Fill in your keys in .env

pip install -r requirements.txt
python main.py
```

Expose locally with [ngrok](https://ngrok.com):

```bash
ngrok http 8000
# Then register the webhook:
curl -X POST http://localhost:8000/set_webhook \
     -H "Content-Type: application/json" \
     -d '{"url": "https://YOUR_NGROK_ID.ngrok.io/webhook"}'
```

---

## Admin Dashboard

Visit `https://your-app.onrender.com/admin`  
Password = first 16 characters of your `SECRET_KEY`

The dashboard shows users, searches, conversation history, and agent execution logs.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | From @BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | Optional | Random string to verify webhook authenticity |
| `GEMINI_API_KEY` | ✅ | Google AI Studio key |
| `SERPAPI_KEY` | ✅ | SerpAPI key for search |
| `DATABASE_URL` | ✅ | PostgreSQL (Render provides) or SQLite for local |
| `SECRET_KEY` | ✅ | Random 32+ char string for Flask sessions |
| `MAX_REQUESTS_PER_USER_PER_HOUR` | Optional | Default 30 |

---

## Supported Query Types

| Intent | Example |
|--------|---------|
| Local business | "Plumbers in Chennai with phone number" |
| Hotels | "Budget hotels near Marina Beach" |
| Restaurants | "Best biryani restaurants in Hyderabad" |
| Hospitals | "Hospitals near Velachery" |
| People/LinkedIn | "Python developers in Bangalore" |
| News | "Latest Tamil Nadu news today" |
| Companies | "IT companies in Chennai" |
| General | "How to get an Aadhaar card" |
