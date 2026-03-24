# backend/agents/email_generator.py

import os
import re
import json
from groq   import Groq
from loguru import logger
from dotenv import load_dotenv
load_dotenv()

client    = Groq(api_key=os.getenv("GROQ_API_KEY"))
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_prompt(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Prompt load error {filename}: {e}")
        return ""


def _clean_email_address(raw: str) -> str:
    """Extract bare email from 'Name <email@domain>' format."""
    if not raw:
        return ""
    match = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', raw)
    return match.group(0) if match else raw.strip()


def _get_resume_path_from_db(user_id: int) -> str:
    """
    DB se user ka resume path fetch karo.
    Hardcoded path assumption hataya — onboarding mein jo path
    save hua tha wahi use hoga.
    """
    try:
        from backend.database    import SessionLocal
        from backend.models.user import UserProfile

        db      = SessionLocal()
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        db.close()

        if profile and profile.resume_path and os.path.exists(profile.resume_path):
            return profile.resume_path

    except Exception as e:
        logger.warning(f"DB resume path fetch error: {e}")

    # Fallback — common paths try karo
    fallbacks = [
        f"uploads/{user_id}/resume_base.pdf",
        f"uploads/{user_id}/resume.pdf",
        f"uploads/{user_id}/cv.pdf",
    ]
    for path in fallbacks:
        if os.path.exists(path):
            return path

    return ""


def get_user_info(user_id: int) -> dict:
    """
    Resume path DB se lo, fir text extract karo,
    fir Groq se name/skills/key_project nikalo.
    """
    resume_path = _get_resume_path_from_db(user_id)

    if not resume_path:
        return {
            "name"       : "Candidate",
            "skills"     : [],
            "key_project": "",
            "resume_path": ""
        }

    resume_text = ""
    try:
        import pdfplumber
        with pdfplumber.open(resume_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    resume_text += text + "\n"
    except Exception as e:
        logger.error(f"PDF read error: {e}")

    if not resume_text:
        return {
            "name"       : "Candidate",
            "skills"     : [],
            "key_project": "",
            "resume_path": resume_path
        }

    try:
        res = client.chat.completions.create(
            model    = LLM_MODEL,
            messages = [
                {
                    "role"   : "system",
                    "content": (
                        "Return ONLY valid JSON. "
                        "No markdown. No explanation. "
                        "No text outside the JSON object."
                    )
                },
                {
                    "role"   : "user",
                    "content": (
                        f"Extract from this resume:\n"
                        f'{{"name":"full name","skills":["skill1","skill2"],'
                        f'"key_project":"most impressive project in 1 line"}}\n\n'
                        f"Resume:\n{resume_text[:2500]}"
                    )
                }
            ],
            max_tokens  = 300,
            temperature = 0.1
        )
        raw    = res.choices[0].message.content.strip()
        parsed = _parse(raw)
        return {
            "name"       : parsed.get("name",        "Candidate"),
            "skills"     : parsed.get("skills",      []),
            "key_project": parsed.get("key_project", ""),
            "resume_path": resume_path,
        }
    except Exception as e:
        logger.error(f"User info extract error: {e}")
        return {
            "name"       : "Candidate",
            "skills"     : [],
            "key_project": "",
            "resume_path": resume_path
        }


# ─────────────────────────────────────────────
# JSON PARSER
# ─────────────────────────────────────────────

def _parse(raw: str) -> dict:
    """Robust JSON parser — handles LLM quirks."""
    raw = raw.replace("```json", "").replace("```", "").strip()

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in: {raw[:200]}")
    raw = raw[start:end]

    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)

    cleaned = []
    in_str  = False
    i       = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\\' and in_str:
            cleaned.append(ch)
            i += 1
            if i < len(raw):
                cleaned.append(raw[i])
        elif ch == '"':
            in_str = not in_str
            cleaned.append(ch)
        elif in_str and ch == '\n':
            cleaned.append('\\n')
        elif in_str and ch == '\t':
            cleaned.append('\\t')
        elif in_str and ch == '\r':
            cleaned.append('\\r')
        else:
            cleaned.append(ch)
        i += 1

    return json.loads("".join(cleaned))


# ─────────────────────────────────────────────
# GROQ CALLER
# ─────────────────────────────────────────────

def call_groq(prompt: str, max_tokens: int = 800) -> dict:
    """
    Call Groq with JSON-enforcing system prompt.
    Two attempts with escalating strictness.
    """
    system = (
        "You MUST return a single valid JSON object. "
        "Rules: (1) No markdown fences. (2) No text before or after the JSON. "
        "(3) All string values must be on ONE line — escape newlines as \\n. "
        "(4) Do NOT truncate — complete every string value and close every bracket."
    )

    for attempt, temp in enumerate([0.6, 0.1], 1):
        try:
            res = client.chat.completions.create(
                model    = LLM_MODEL,
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt}
                ],
                max_tokens  = max_tokens,
                temperature = temp
            )
            raw    = res.choices[0].message.content.strip()
            result = _parse(raw)
            if result.get("subject") and result.get("body"):
                return result
            logger.warning(
                f"Attempt {attempt}: missing subject/body, retrying"
            )
        except Exception as e:
            logger.warning(f"Attempt {attempt} failed: {e}")

    logger.error("Both Groq attempts failed — returning empty")
    return {}


def get_optimized_resume_path(user_id: int, name: str) -> str:
    safe = (
        name.lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace(".", "_")[:30]
    )
    return os.path.join(
        "uploads", str(user_id), "resumes", f"{safe}_resume.pdf"
    )


# ─────────────────────────────────────────────
# TYPE 1 — Cold Email
# Research data (ai_hook, recent_highlight, tech_stack)
# now passed in and injected into prompt for personalisation.
# ─────────────────────────────────────────────

def generate_cold_email(
    user_id         : int,
    company         : str,
    description     : str,
    one_liner       : str,
    contact         : dict,
    ai_hook         : str  = "",
    recent_highlight: str  = "",
    tech_stack      : list = None,
) -> dict:
    user_info       = get_user_info(user_id)
    prompt_template = load_prompt("cold_email_prompt.txt")

    if not prompt_template:
        return {"error": "cold_email_prompt.txt missing"}

    tech_stack_str = ", ".join(tech_stack) if tech_stack else ""

    prompt = prompt_template.format(
        user_name           = user_info["name"],
        contact_name        = contact.get("name",  "Founder"),
        contact_role        = contact.get("role",  "Founder"),
        company_name        = company,
        one_liner           = one_liner,
        company_description = description[:400],
        user_skills         = ", ".join(user_info["skills"][:10]),
        key_project         = user_info["key_project"],
        # Research-enriched fields for personalisation
        ai_hook             = ai_hook          or "N/A",
        recent_highlight    = recent_highlight or "N/A",
        tech_stack          = tech_stack_str   or "N/A",
    )

    result = call_groq(prompt)
    if not result:
        return {"error": "Email generation failed"}

    resume_path = get_optimized_resume_path(user_id, company)
    if not os.path.exists(resume_path):
        resume_path = user_info["resume_path"]

    return {
        "subject"      : result.get("subject",  ""),
        "body"         : result.get("body",      ""),
        "gap"          : result.get("gap",       ""),
        "proposal"     : result.get("proposal",  ""),
        "why_fits"     : result.get("why_fits",  ""),
        "contact_name" : contact.get("name",     ""),
        "contact_role" : contact.get("role",     ""),
        "contact_email": _clean_email_address(contact.get("email", "")),
        "resume_path"  : resume_path,
    }


# ─────────────────────────────────────────────
# TYPE 2 — Follow Up Email
# ─────────────────────────────────────────────

def generate_followup_email(
    user_id         : int,
    company         : str,
    contact         : dict,
    original_subject: str,
    original_body   : str,
    days_ago        : int
) -> dict:
    user_info       = get_user_info(user_id)
    prompt_template = load_prompt("followup_prompt.txt")

    if not prompt_template:
        return {"error": "followup_prompt.txt missing"}

    prompt = prompt_template.format(
        user_name        = user_info["name"],
        company_name     = company,
        contact_name     = contact.get("name", "Founder"),
        contact_role     = contact.get("role", ""),
        days_ago         = days_ago,
        original_subject = original_subject,
        original_proposal= original_body[:200],
    )

    result = call_groq(prompt, max_tokens=400)
    if not result:
        return {"error": "Followup generation failed"}

    return {
        "subject"        : result.get("subject",         f"Re: {original_subject}"),
        "body"           : result.get("body",            ""),
        "new_value_added": result.get("new_value_added", ""),
        "contact_email"  : _clean_email_address(contact.get("email", "")),
    }