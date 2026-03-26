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
    """DB se user ka resume path fetch karo."""
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
    for path in [
        f"uploads/{user_id}/resume_base.pdf",
        f"uploads/{user_id}/resume.pdf",
        f"uploads/{user_id}/cv.pdf",
    ]:
        if os.path.exists(path):
            return path

    return ""


def get_user_info(user_id: int) -> dict:
    """Resume se name/skills/key_project extract karo via Groq."""
    resume_path = _get_resume_path_from_db(user_id)

    _default = {
        "name"       : "Candidate",
        "skills"     : [],
        "key_project": "",
        "resume_path": resume_path,
    }

    if not resume_path:
        return _default

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
        return _default

    try:
        res = client.chat.completions.create(
            model    = LLM_MODEL,
            messages = [
                {
                    "role"   : "system",
                    "content": (
                        "Extract from this resume and return ONLY a single-line JSON object. "
                        "No newlines inside values. No markdown. Exact format:\n"
                        '{"name":"John Doe","skills":["Python","FastAPI"],"key_project":"Built RAG chatbot"}'
                    )
                },
                {
                    "role"   : "user",
                    "content": f"Resume:\n{resume_text[:2500]}"
                }
            ],
            max_tokens  = 300,
            temperature = 0.1,
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
        return _default


# ─────────────────────────────────────────────
# JSON PARSER  (robust — handles all LLM quirks)
# ─────────────────────────────────────────────

def _parse(raw: str) -> dict:
    """
    Handles:
    - ```json ... ``` fences
    - Text before/after the JSON object
    - Unescaped newlines / tabs inside string values
    - Truncated responses (tries to salvage with regex)
    """
    if not raw:
        raise ValueError("Empty response from LLM")

    # 1. Strip markdown fences
    raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()

    # 2. Find outermost { ... }
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end <= start:
        # Last resort — try to extract key fields with regex
        return _salvage(raw)

    raw = raw[start:end]

    # 3. Strip control characters (except \n \t \r which we'll handle)
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)

    # 4. Fix unescaped newlines/tabs inside string values
    cleaned = []
    in_str  = False
    i       = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\\' and in_str:
            # Keep escape sequence intact
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

    try:
        return json.loads("".join(cleaned))
    except json.JSONDecodeError as e:
        logger.warning(f"json.loads failed ({e}), trying salvage...")
        return _salvage(raw)


def _salvage(raw: str) -> dict:
    """
    Regex-based last resort — extract subject/body/gap/proposal
    even from a malformed or truncated JSON string.
    """
    result = {}
    for key in ("subject", "body", "gap", "proposal", "why_fits",
                "new_value_added"):
        # Match "key": "value"  OR  "key": "value (truncated)
        pattern = rf'"{key}"\s*:\s*"(.*?)(?:"|$)'
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            result[key] = m.group(1).replace("\\n", "\n").strip()

    if not result:
        raise ValueError(f"Could not salvage any fields from: {raw[:300]}")
    return result


# ─────────────────────────────────────────────
# GROQ CALLER
# ─────────────────────────────────────────────

def call_groq(prompt: str, max_tokens: int = 800) -> dict:
    """
    Call Groq with strict JSON system prompt.
    3 attempts: temp 0.6 → 0.3 → 0.1 (escalating strictness).
    Returns {} only if all attempts fail.
    """
    system = (
        "You MUST return a single valid JSON object and NOTHING else. "
        "Rules:\n"
        "1. No markdown fences (no ```json).\n"
        "2. No text before or after the JSON.\n"
        "3. All string values must be on ONE line — escape newlines as \\n.\n"
        "4. Do NOT truncate — complete every string and close every bracket.\n"
        "5. Start your response with { and end with }."
    )

    for attempt, temp in enumerate([0.6, 0.3, 0.1], 1):
        try:
            res = client.chat.completions.create(
                model    = LLM_MODEL,
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens  = max_tokens,
                temperature = temp,
            )
            raw = res.choices[0].message.content.strip()
            logger.debug(f"Groq attempt {attempt} raw ({len(raw)} chars): {raw[:120]}...")

            result = _parse(raw)

            # Validate required fields exist and are non-empty
            if result.get("subject") and result.get("body"):
                logger.info(f"Groq success on attempt {attempt}")
                return result

            logger.warning(
                f"Attempt {attempt}: parsed OK but subject/body missing — "
                f"keys found: {list(result.keys())}"
            )

        except Exception as e:
            logger.warning(f"Attempt {attempt} failed: {e}")

    logger.error("All 3 Groq attempts failed — returning empty dict")
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
        ai_hook             = ai_hook          or "N/A",
        recent_highlight    = recent_highlight or "N/A",
        tech_stack          = tech_stack_str   or "N/A",
    )

    result = call_groq(prompt)
    if not result:
        return {"error": "Email generation failed after 3 attempts"}

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
    days_ago        : int,
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
        return {"error": "Followup generation failed after 3 attempts"}

    return {
        "subject"        : result.get("subject",         f"Re: {original_subject}"),
        "body"           : result.get("body",            ""),
        "new_value_added": result.get("new_value_added", ""),
        "contact_email"  : _clean_email_address(contact.get("email", "")),
    }