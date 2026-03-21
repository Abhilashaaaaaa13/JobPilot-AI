# backend/agents/email_generator.py

import os
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


def get_user_info(user_id: int) -> dict:
    """
    User ka resume se naam + skills + key project nikalo.
    DB nahi — directly resume file se.
    """
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
    "key_project": "most impressive project in 1 line under 20 words — what built + tech + result"
}}

Resume:
{resume_text[:3000]}
"""
            }],
            max_tokens  = 300,
            temperature = 0.1
        )
        raw    = res.choices[0].message.content.strip()
        raw    = raw.replace("```json","").replace("```","").strip()
        parsed = json.loads(raw)

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


def call_groq(prompt: str, max_tokens: int = 600) -> dict:
    try:
        res = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = max_tokens,
            temperature= 0.7
        )
        raw = res.choices[0].message.content.strip()
        raw = raw.replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Groq JSON parse failed")
        return {}
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return {}


def get_optimized_resume_path(user_id: int, name: str) -> str:
    """Company ke liye optimized resume path."""
    safe = name.lower()\
               .replace(" ","_")\
               .replace("/","_")\
               .replace(".","_")[:30]
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
    """
    Cold email — gap + proposal angle.
    Prompt: backend/prompts/cold_email_prompt.txt

    Args:
        user_id    : int
        company    : "Playabl.ai"
        description: full description
        one_liner  : "AI game builder for everyone"
        contact    : {name, role, email}
    """
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

    # Optimized resume path check
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
        "contact_email": contact.get("email",    ""),
        "resume_path"  : resume_path
    }


# ─────────────────────────────────────────────
# TYPE 2 — Job Application Email
# ─────────────────────────────────────────────

def generate_job_email(
    user_id   : int,
    job_title : str,
    company   : str,
    job_desc  : str,
    contact   : dict = None
) -> dict:
    """
    Job application email.
    Prompt: backend/prompts/job_email_prompt.txt

    Args:
        user_id  : int
        job_title: "AI Engineer"
        company  : "Anthropic"
        job_desc : job description text
        contact  : optional {name, role, email}
    """
    user_info       = get_user_info(user_id)
    prompt_template = load_prompt("job_email_prompt.txt")

    if not prompt_template:
        logger.error("job_email_prompt.txt nahi mila")
        return {"error": "Prompt file missing"}

    contact_name  = contact.get("name",  "Hiring Manager") if contact else "Hiring Manager"
    contact_role  = contact.get("role",  "")               if contact else ""
    contact_email = contact.get("email", "")               if contact else ""

    prompt = prompt_template.format(
        user_name        = user_info["name"],
        contact_name     = contact_name,
        contact_role     = contact_role,
        company_name     = company,
        job_title        = job_title,
        job_description  = job_desc[:600],
        user_skills      = ", ".join(user_info["skills"][:10]),
        key_project      = user_info["key_project"],
        experience_years = 0,
        company_summary  = "",
        tech_stack       = ""
    )

    result = call_groq(prompt)

    if not result:
        return {"error": "Email generation failed"}

    resume_path = get_optimized_resume_path(user_id, company)
    if not os.path.exists(resume_path):
        resume_path = user_info["resume_path"]

    return {
        "subject"       : result.get("subject",              ""),
        "body"          : result.get("body",                  ""),
        "core_problem"  : result.get("core_problem_identified",""),
        "idea_suggested": result.get("idea_suggested",        ""),
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
    """
    Follow up — new value add karo.
    Prompt: backend/prompts/followup_prompt.txt

    Args:
        user_id         : int
        company         : company name
        contact         : {name, role, email}
        original_subject: original email subject
        original_body   : original email body (first 200 chars)
        days_ago        : int — kitne din pehle bheja tha
    """
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

    return {
        "subject"        : result.get("subject",         f"Re: {original_subject}"),
        "body"           : result.get("body",            ""),
        "new_value_added": result.get("new_value_added", ""),
        "contact_email"  : contact.get("email",          "")
    }