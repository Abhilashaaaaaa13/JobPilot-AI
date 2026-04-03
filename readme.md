# OutreachAI

Automated cold outreach pipeline for job seekers targeting startups. Find companies, research them, generate personalized emails, send via Gmail, auto follow-up, and track replies — all from one interface.

---

## What it does

- Scrapes fresh startups from YC, Betalist, and Product Hunt
- Researches each company — website content, recent news, tech stack, AI angle
- Finds decision-maker contacts (CEO, CTO, Founders) via team page scraping and Hunter.io
- Generates personalized cold emails using Groq (Llama 3.3-70b) based on your resume and company research
- Sends emails through your own Gmail account with resume attached
- Auto follow-up on day 4 and day 7 if no reply
- Detects incoming replies via Gmail IMAP and auto-drafts responses for your approval
- Tracks everything — sent emails, reply rate, follow-up history

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Streamlit |
| Pipeline | LangGraph |
| LLM | Groq — Llama 3.3-70b-versatile |
| Database | SQLite + SQLAlchemy |
| Email send/receive | Gmail SMTP + IMAP |
| Scraping | Playwright, BeautifulSoup, requests |
| Web search | DuckDuckGo, Tavily |
| Scheduler | APScheduler |
| Email lookup | Hunter.io + pattern generation |

---

## Project Structure

```
outreachai/
│
├── run_scheduler.py
│
├── frontend/
│   ├── app.py                    # Login, dashboard, startup feed
│   └── pages/
│       ├── 2_onboarding.py       # Resume upload + preferences
│       ├── 3_replies.py          # Reply detection + draft approvals
│       ├── 4_outreach.py         # Company cards + email drafting
│       └── 5_tracker.py          # Sent email log + stats
│
├── backend/
│   ├── config.py
│   ├── database.py
│   │
│   ├── agents/
│   │   ├── scraper_agent.py      # YC + Betalist + Product Hunt scraping
│   │   ├── research_agent.py     # Website + news + Groq summary
│   │   ├── contact_finder.py     # Team page scraping + email finding
│   │   ├── email_generator.py    # Cold email + followup generation
│   │   ├── email_sender.py       # Gmail SMTP + JSON log
│   │   ├── feed_agent.py         # Global company feed
│   │   └── followup_agent.py     # Auto follow-up logic
│   │
│   ├── pipeline/
│   │   ├── graph.py              # LangGraph StateGraph
│   │   ├── nodes.py              # Pipeline node functions
│   │   ├── state.py              # TrackBState TypedDict
│   │   ├── reply_handler.py      # IMAP detection + auto-draft
│   │   ├── reply_nodes.py        # LangGraph nodes for reply flow
│   │   └── scheduler.py          # APScheduler job definitions
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── company.py
│   │   ├── contact.py
│   │   ├── sent_email.py
│   │   ├── notification.py
│   │   └── draft_action.py
│   │
│   └── utils/
│       ├── auth_utils.py
│       ├── email_verifier.py
│       ├── feed_to_db.py
│       ├── pdf_parser.py
│       └── sheets_tracker.py     # Google Sheets sync (optional)
│
├── data/
│   └── company_feed.json
│
├── uploads/
│   └── {user_id}/
│       ├── resume_base.pdf
│       └── sent_emails/
│           └── log.json
│
└── prompts/
    ├── cold_email_prompt.txt
    └── followup_prompt.txt
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourusername/outreachai.git
cd outreachai

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### 2. Environment variables

Create a `.env` file in the project root:

```env
# Required
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=llama-3.3-70b-versatile

# Optional — improves email finding
HUNTER_API_KEY=your_hunter_api_key
APOLLO_API_KEY=your_apollo_api_key

# Optional — better company research
TAVILY_API_KEY=your_tavily_api_key

# Optional — Product Hunt feed
PRODUCT_HUNT_TOKEN=your_ph_token

# Optional — Google Sheets tracking
GOOGLE_SHEETS_ID=your_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=credentials.json

# Follow-up timing (these are the defaults)
FOLLOWUP_AFTER_DAYS=4
FOLLOWUP_2_AFTER_DAYS=7
MAX_FOLLOWUPS=2
```

### 3. Gmail App Password

OutreachAI sends and receives emails through your Gmail account using an App Password. Your actual Gmail password is never stored.

1. Go to myaccount.google.com > Security
2. Enable 2-Step Verification
3. Go to App Passwords > select Mail > Generate
4. Copy the 16-character password
5. Enter it in the app under Profile Setup

### 4. Run

```bash
# Terminal 1 — keeps follow-ups and reply detection running in background
python run_scheduler.py

# Terminal 2 — the app
streamlit run frontend/app.py
```

Open `http://localhost:8501`.

---

## Usage

**First time:**
1. Register an account
2. Go to Profile Setup — upload your resume PDF and set your preferences (target roles, domains, location)
3. Add your Gmail address and App Password

**Daily workflow:**
1. Open Dashboard — fresh startups appear in the feed
2. Click Outreach on any company — email is drafted automatically
3. Review and send
4. Scheduler handles follow-ups on day 4 and day 7
5. Check Replies & Drafts when someone responds — approve or edit the AI-drafted reply before it sends

---

## Pipeline

```
Select companies
      |
      v
Research companies
  - scrape website
  - search recent news (Tavily / DuckDuckGo)
  - Groq summary: ai_hook, recent_highlight, tech_stack
      |
      v
Generate emails
  - Groq generates subject, body, gap identified, proposal
  - resume fetched from DB
      |
      v
[user reviews emails]
      |
      v
Send emails
  - Gmail SMTP
  - logged to sent_emails/log.json
  - synced to Google Sheets (if configured)
```

### Scheduler jobs

| Job | Runs every | What it does |
|---|---|---|
| Reply check | 12 hours | IMAP scan, detect replies, auto-draft response, create notification |
| Follow-up | 4 days | Find unreplied emails past threshold, generate and send follow-up |
| Feed refresh | 24 hours | Scrape YC + Betalist + Product Hunt, update company_feed.json |

---

## Email finding

For each contact found on a company's team page:

```
1. Website scraping     verified = True    free, no limits
2. Hunter.io API        verified = True    25 free searches/month
3. Pattern generation   verified = False   firstname.lastname@domain.com
```

---

## API Keys

| Key | Where to get | Free tier |
|---|---|---|
| GROQ_API_KEY | console.groq.com | Yes |
| HUNTER_API_KEY | hunter.io | 25 searches/month |
| TAVILY_API_KEY | tavily.com | 1000 searches/month |
| APOLLO_API_KEY | apollo.io | Limited |
| PRODUCT_HUNT_TOKEN | api.producthunt.com/v2/oauth/applications | Yes |

---

## Known limitations

- Betalist scraping uses Playwright (headless browser) and can take 30-60 seconds
- Pattern-guessed emails have no verification — some will bounce
- Reply detection matches by sender domain and subject line — edge cases with forwarded emails are possible
- The scheduler (`run_scheduler.py`) must be running for auto follow-ups and reply detection to work. Use `nohup python run_scheduler.py > scheduler.log 2>&1 &` to keep it alive after closing the terminal

---

## Roadmap

- Company auto-scoring based on tech stack match and team size
- LinkedIn contact scraping
- Email open and click tracking
- One-click deploy to Railway or Render

---

## License

MIT