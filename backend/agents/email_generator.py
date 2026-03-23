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

PROMPTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "prompts"
)


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
    """
    FIX — Email address se angle brackets strip karo.

    'To' headers often come as: "Name <email@domain.com>"
    Naively str()-ing them produces: u003eemail@domain.com
    (because < is dropped and > becomes its unicode escape u003e)

    This extracts just the bare email address.
    """
    if not raw:
        return raw
    # "Name <email@domain>" → "email@domain"
    match = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', raw)
    return match.group(0) if match else raw.strip()


def get_user_info(user_id: int) -> dict:
    resume_path = f"uploads/{user_id}/resume_base.pdf"

    if not os.path.exists(resume_path):
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
            messages = [{
                "role"   : "user",
                "content": f"""
Extract from this resume. Return ONLY JSON, no markdown:
{{
    "name"       : "full name from resume",
    "skills"     : ["skill1", "skill2", "skill3"],
    "key_project": "most impressive project in 1 line under 20 words"
}}

Resume:
{resume_text[:3000]}
"""
            }],
            max_tokens  = 300,
            temperature = 0.1
        )
        raw    = res.choices[0].message.content.strip()
        parsed = _parse(raw)

        return {
            "name"       : parsed.get("name",        "Candidate"),
            "skills"     : parsed.get("skills",      []),
            "key_project": parsed.get("key_project", ""),
            "resume_path": resume_path
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
# JSON PARSER (shared by all Groq calls)
# ─────────────────────────────────────────────

def _parse(raw: str) -> dict:
    """
    Groq response ko clean karke JSON parse karo.

    FIX — Control characters and bare newlines inside JSON string values
    cause json.loads to raise:
      "Invalid control character at: line N column M"
      "Expecting ',' delimiter: ..."

    Steps:
    1. Strip markdown fences
    2. Extract JSON object boundaries
    3. Remove ASCII control chars (0x00–0x1F) EXCEPT tab/newline/CR
       which are valid JSON whitespace outside strings
    4. Replace bare newlines/tabs that landed INSIDE string values
    """
    # 1. Strip markdown
    raw = raw.replace("```json", "").replace("```", "").strip()

    # 2. Extract outermost { ... }
    if not raw.startswith("{"):
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]

    # 3. Remove non-printable control characters (keep \t \n \r)
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)

    # 4. Replace bare (unescaped) newlines and tabs inside string values.
    #    We do a simple state-machine scan: inside a JSON string literal,
    #    a literal \n must be written as \\n.
    cleaned = []
    in_str  = False
    i       = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\\' and in_str:
            # Escaped character — copy both chars verbatim
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

def call_groq(prompt: str, max_tokens: int = 600) -> dict:
    """
    Groq call karo — JSON parse karo.
    Agar fail → retry with stricter system prompt.
    """
    # Attempt 1
    try:
        res = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = max_tokens,
            temperature= 0.7
        )
        raw = res.choices[0].message.content.strip()
        return _parse(raw)

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"First attempt failed: {e} — retrying...")

    # Attempt 2 — explicit system prompt + lower temperature
    try:
        res2 = client.chat.completions.create(
            model    = LLM_MODEL,
            messages = [
                {
                    "role"   : "system",
                    "content": (
                        "Return ONLY a valid JSON object. "
                        "No markdown, no code fences, no explanation. "
                        "No text before or after the JSON. "
                        "All string values must be on a single line — "
                        "do NOT include literal newlines inside string values."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens  = max_tokens,
            temperature = 0.1
        )
        raw2 = res2.choices[0].message.content.strip()
        return _parse(raw2)

    except Exception as e:
        logger.error(f"Both attempts failed: {e}", exc_info=True)
        return {}


def get_optimized_resume_path(user_id: int, name: str) -> str:
    safe = name.lower()\
               .replace(" ", "_")\
               .replace("/", "_")\
               .replace(".", "_")[:30]
    return os.path.join(
        "uploads", str(user_id), "resumes", f"{safe}_resume.pdf"
    )


# ─────────────────────────────────────────────
# TYPE 1 — Cold Email
# ─────────────────────────────────────────────

def generate_cold_email(
    user_id    : int,
    company    : str,
    description: str,
    one_liner  : str,
    contact    : dict
) -> dict:
    user_info       = get_user_info(user_id)
    prompt_template = load_prompt("cold_email_prompt.txt")

    if not prompt_template:
        logger.error("cold_email_prompt.txt nahi mila")
        return {"error": "Prompt file missing"}

    prompt = prompt_template.format(
        user_name          = user_info["name"],
        contact_name       = contact.get("name",  "Founder"),
        contact_role       = contact.get("role",  "Founder"),
        company_name       = company,
        one_liner          = one_liner,
        company_description= description[:400],
        user_skills        = ", ".join(user_info["skills"][:10]),
        key_project        = user_info["key_project"],
    )

    result = call_groq(prompt)
    if not result:
        return {"error": "Email generation failed"}

    resume_path = get_optimized_resume_path(user_id, company)
    if not os.path.exists(resume_path):
        resume_path = user_info["resume_path"]

    # FIX — clean contact email before returning
    raw_email = contact.get("email", "")
    return {
        "subject"      : result.get("subject",  ""),
        "body"         : result.get("body",      ""),
        "gap"          : result.get("gap",       ""),
        "proposal"     : result.get("proposal",  ""),
        "why_fits"     : result.get("why_fits",  ""),
        "contact_name" : contact.get("name",     ""),
        "contact_role" : contact.get("role",     ""),
        "contact_email": _clean_email_address(raw_email),
        "resume_path"  : resume_path
    }


# ─────────────────────────────────────────────
# TYPE 2 — Job Application Email
# ─────────────────────────────────────────────

def generate_job_email(
    user_id         : int,
    job_title       : str,
    company         : str,
    job_desc        : str,
    contact         : dict = None,
    experience_years: int  = 0,    # FIX — accept from caller instead of hardcoding
    company_summary : str  = "",
    tech_stack      : str  = ""
) -> dict:
    user_info       = get_user_info(user_id)
    prompt_template = load_prompt("job_email_prompt.txt")

    if not prompt_template:
        logger.error("job_email_prompt.txt nahi mila")
        return {"error": "Prompt file missing"}

    contact_name  = contact.get("name",  "Hiring Manager") if contact else "Hiring Manager"
    contact_role  = contact.get("role",  "")               if contact else ""
    raw_email     = contact.get("email", "")               if contact else ""
    contact_email = _clean_email_address(raw_email)        # FIX — clean on the way out

    prompt = prompt_template.format(
        user_name        = user_info["name"],
        contact_name     = contact_name,
        contact_role     = contact_role,
        company_name     = company,
        job_title        = job_title,
        job_description  = job_desc[:600],
        user_skills      = ", ".join(user_info["skills"][:10]),
        key_project      = user_info["key_project"],
        experience_years = experience_years,
        company_summary  = company_summary,
        tech_stack       = tech_stack
    )

    result = call_groq(prompt)
    if not result:
        return {"error": "Email generation failed"}

    resume_path = get_optimized_resume_path(user_id, company)
    if not os.path.exists(resume_path):
        resume_path = user_info["resume_path"]

    return {
        "subject"       : result.get("subject",                ""),
        "body"          : result.get("body",                    ""),
        "core_problem"  : result.get("core_problem_identified", ""),
        "idea_suggested": result.get("idea_suggested",          ""),
        "contact_name"  : contact_name,
        "contact_role"  : contact_role,
        "contact_email" : contact_email,
        "resume_path"   : resume_path
    }


# ─────────────────────────────────────────────
# TYPE 3 — Follow Up Email
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
        logger.error("followup_prompt.txt nahi mila")
        return {"error": "Prompt file missing"}

    prompt = prompt_template.format(
        user_name        = user_info["name"],
        company_name     = company,
        contact_name     = contact.get("name", "Founder"),
        contact_role     = contact.get("role", ""),
        days_ago         = days_ago,
        original_subject = original_subject,
        original_proposal= original_body[:200]
    )

    result = call_groq(prompt, max_tokens=400)
    if not result:
        return {"error": "Followup generation failed"}

    raw_email = contact.get("email", "")
    return {
        "subject"        : result.get("subject",         f"Re: {original_subject}"),
        "body"           : result.get("body",            ""),
        "new_value_added": result.get("new_value_added", ""),
        "contact_email"  : _clean_email_address(raw_email)   # FIX — clean here too
    }