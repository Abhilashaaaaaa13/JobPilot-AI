# JobPilot AI

Automated cold outreach for job seekers targeting startups. Find companies, research them, generate personalized emails grounded in your actual resume, send via your own Gmail, auto follow-up, and track replies — all from one app.

React frontend + FastAPI backend, single SQLite database, deployable as one Docker container.

---

## What it does

- Scrapes fresh startups in parallel from 6 sources — YC, Betalist, Product Hunt, Indie Hackers, GitHub Trending, HN Hiring — with live per-source progress shown in the UI, and newly-found companies flagged and sorted to the top
- Finds decision-maker contacts (CEO, CTO, Founders) via website scraping, Hunter.io, and pattern generation
- Generates personalized cold emails with Groq — grounded in your real resume skills/projects and a specific gap in the target company's product, framed as either a new feature or an upgrade to something they already have, not a generic "about me" bio
- Sends emails through your own Gmail account (App Password) with resume attached
- Auto follow-up if no reply after a few days
- Detects incoming replies via Gmail IMAP and auto-drafts responses for your approval
- Tracks everything in-app, and optionally syncs to Google Sheets — each account can point at its own sheet, or share the default one
- Background scheduler (reply checks, follow-ups, Sheets sync) controllable from the UI — auto-starts on login, Start/Stop toggle in the sidebar

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React (Vite) + Tailwind CSS |
| Backend API | FastAPI, JWT auth |
| LLM | Groq — `openai/gpt-oss-20b` |
| Database | SQLite + SQLAlchemy |
| Email send/receive | Gmail SMTP + IMAP |
| Scraping | Playwright, BeautifulSoup, requests — 6 sources run in parallel |
| Scheduler | APScheduler, runs in-process, controlled from the UI |
| Email lookup | Website scraping, Hunter.io, pattern generation |
| Deploy | Docker (multi-stage: builds the React app, serves it from FastAPI as one service) |

A legacy Streamlit UI still lives in `frontend/` for reference, but the React app (`client/` + `backend/api/`) is the one actively developed and deployed.

---

## Project Structure

```
jobpilot-ai/
│
├── client/                       # React (Vite + Tailwind) frontend
│   └── src/
│       ├── pages/                # Login, Dashboard, Profile, Outreach, Tracker, Replies
│       ├── components/           # Sidebar, CompanyCard, EmailPanel, etc.
│       └── api.js                # Fetch client, attaches JWT
│
├── backend/
│   ├── config.py
│   ├── database.py
│   │
│   ├── api/                      # FastAPI app — thin HTTP layer over backend/*
│   │   ├── main.py               # App setup, serves client/dist
│   │   ├── auth.py                # JWT helpers
│   │   └── routes_*.py           # auth, profile, companies, tracker, replies, scheduler
│   │
│   ├── agents/
│   │   ├── scraper_agent.py      # 6-source parallel scraping + email finding
│   │   ├── research_agent.py     # Website + news + Groq summary
│   │   ├── contact_finder.py     # Team page scraping + email finding
│   │   ├── email_generator.py    # Cold email + followup generation
│   │   ├── email_sender.py       # Gmail SMTP + JSON log
│   │   ├── feed_agent.py         # Per-user company feed refresh
│   │   └── followup_agent.py     # Auto follow-up logic
│   │
│   ├── pipeline/
│   │   ├── reply_handler.py      # IMAP detection + auto-draft + approval
│   │   └── scheduler.py          # APScheduler job definitions
│   │
│   ├── models/                   # SQLAlchemy models
│   │
│   └── utils/
│       ├── auth_utils.py
│       ├── feed_to_db.py
│       ├── pdf_parser.py
│       └── sheets_tracker.py     # Google Sheets sync, per-user or shared
│
├── frontend/                     # Legacy Streamlit UI (kept for reference)
│
├── data/                         # SQLite DB + cached feed JSON
├── uploads/{user_id}/            # Resumes + sent-email logs
├── prompts/                      # Cold email + followup prompt templates
│
├── Dockerfile                    # Multi-stage: build client, serve via FastAPI
├── Procfile                      # Railway-style single-command deploy
├── render.yaml                   # Render Blueprint deploy
└── start_app.bat                 # Windows: double-click to start the server
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Abhilashaaaaaa13/JobPilot-AI.git
cd JobPilot-AI

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium

cd client
npm install
npm run build
cd ..
```

### 2. Environment variables

Create a `.env` file in the project root:

```env
# Required
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=openai/gpt-oss-20b
SECRET_KEY=change-me-to-something-random

# Optional — improves email finding
HUNTER_API_KEY=your_hunter_api_key
APOLLO_API_KEY=your_apollo_api_key

# Optional — better company research
TAVILY_API_KEY=your_tavily_api_key

# Optional — Product Hunt feed
PRODUCT_HUNT_TOKEN=your_ph_token

# Optional — default Google Sheets tracking (users can override their own in Profile Setup)
GOOGLE_SHEETS_ID=your_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=credentials.json
```

### 3. Gmail App Password

Emails send and receive through your Gmail account using an App Password — your real Gmail password is never stored.

1. Go to myaccount.google.com → Security
2. Enable 2-Step Verification
3. Go to App Passwords → select Mail → Generate
4. Copy the 16-character password
5. Enter it in the app under Profile Setup

### 4. Run

```bash
venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

Windows users can just double-click `start_app.bat` instead. Then open `http://localhost:8000` — the background scheduler (reply checks, follow-ups, Sheets sync) starts automatically once you're logged in; toggle it from the sidebar.

---

## Deploy

A `Dockerfile` builds the React app and serves everything (API + UI) as a single container — no separate frontend hosting, no CORS to configure. Works on any Docker-friendly host:

- **Render** — `render.yaml` is included; New → Blueprint, point it at this repo.
- **Railway** — `Procfile` is included as a fallback if the Dockerfile isn't auto-detected.
- Anywhere else that builds from a `Dockerfile`.

Set the same environment variables from `.env` in your host's dashboard — `.env` itself is gitignored and never pushed.

⚠️ Unless your host gives you a persistent volume, container storage is ephemeral — the SQLite DB and uploaded resumes won't survive a redeploy without one.

---

## Usage

**First time:**
1. Register an account
2. Go to Profile Setup — upload your resume PDF (skills/project are extracted automatically) and set your preferences
3. Add your Gmail address and App Password
4. (Optional) Add your own Google Sheet ID to track outreach separately from other accounts

**Daily workflow:**
1. Open Dashboard or Cold Outreach — click "Find More Startups" to scrape fresh companies (live progress shown per source)
2. Open a company card, click "Draft Email" — generated on the spot, edit if you want
3. Send — logged to the Tracker and synced to Google Sheets automatically
4. Scheduler handles follow-ups and reply checks in the background
5. Check Replies & Drafts when someone responds — approve or edit the AI-drafted reply before it sends

---

## Email finding

For each contact found on a company's site:

```
1. Website scraping     verified = True    free, no limits
2. Hunter.io API        verified varies    free tier limited
3. Pattern generation    verified = False   firstname.lastname@domain.com
```

---

## API Keys

| Key | Where to get | Free tier |
|---|---|---|
| GROQ_API_KEY | console.groq.com | Yes |
| HUNTER_API_KEY | hunter.io | Limited |
| TAVILY_API_KEY | tavily.com | 1000 searches/month |
| APOLLO_API_KEY | apollo.io | Limited |
| PRODUCT_HUNT_TOKEN | api.producthunt.com/v2/oauth/applications | Yes |

---

## Known limitations

- Betalist scraping uses Playwright (headless browser) and is the slowest of the 6 sources
- Pattern-guessed emails have no verification — some will bounce
- Reply detection matches by sender address against unreplied sent emails — edge cases with forwarded/CC'd threads are possible
- Container storage is ephemeral on most free hosting tiers — see Deploy section above

---

## License

MIT
