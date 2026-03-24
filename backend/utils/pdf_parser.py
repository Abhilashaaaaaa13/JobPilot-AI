# backend/utils/pdf_parser.py

import pdfplumber
import re
import json
from groq import Groq
from backend.config import GROQ_API_KEY, LLM_MODEL

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except:
    nlp = None

client = Groq(api_key=GROQ_API_KEY)

TECH_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "golang",
    "react", "nextjs", "nodejs", "fastapi", "django", "flask",
    "langchain", "langgraph", "rag", "llm", "nlp",
    "machine learning", "deep learning", "tensorflow", "pytorch",
    "scikit-learn", "pandas", "numpy", "sql", "postgresql",
    "mongodb", "redis", "sqlite", "chromadb", "pinecone",
    "vector db", "docker", "kubernetes", "aws", "gcp", "azure",
    "git", "linux", "rest api", "graphql", "html", "css", "tailwind"
]


def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF read error: {e}")
    return text.strip()


def extract_skills_from_text(text: str) -> list:
    text_lower = text.lower()
    found = []

    for skill in TECH_SKILLS:
        if skill in text_lower:
            found.append(skill.title())

    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in ["ORG", "PRODUCT"]:
                if ent.text not in found:
                    found.append(ent.text)

    return list(set(found))


def extract_experience_years(text: str) -> int:
    text_lower = text.lower()

    if "fresher" in text_lower or "0 year" in text_lower:
        return 0

    pattern = r'(\d+)\+?\s*years?\s*of\s*experience'
    matches = re.findall(pattern, text_lower)
    if matches:
        return int(matches[0])

    pattern2 = r'(\d+)\+?\s*years?'
    matches2 = re.findall(pattern2, text_lower)
    if matches2:
        return int(matches2[0])

    return 0


def parse_resume_with_groq(text: str) -> dict:
    prompt = f"""
Extract information from this resume and return ONLY a JSON object.
No explanation, no markdown, just pure JSON.

Resume:
{text[:3000]}

Return this exact structure:
{{
    "name": "full name or null",
    "email": "email or null",
    "phone": "phone or null",
    "linkedin": "linkedin url or null",
    "github": "github url or null",
    "education": "highest degree and college or null",
    "experience_years": 0,
    "current_role": "current or most recent role or null",
    "skills": ["skill1", "skill2"]
}}
"""
    try:
        response = client.chat.completions.create(
            model       = LLM_MODEL,
            messages    = [{"role": "user", "content": prompt}],
            max_tokens  = 500,
            temperature = 0.1
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"Groq parse error: {e}")
        return {}


def parse_resume(pdf_path: str) -> dict:
    text = extract_text_from_pdf(pdf_path)
    if not text:
        return {"error": "PDF se text extract nahi hua"}

    groq_data      = parse_resume_with_groq(text)
    keyword_skills = extract_skills_from_text(text)
    groq_skills    = groq_data.get("skills", [])
    all_skills     = list(set(groq_skills + keyword_skills))

    exp = groq_data.get("experience_years", 0)
    if exp == 0:
        exp = extract_experience_years(text)

    return {
        "name"            : groq_data.get("name"),
        "email"           : groq_data.get("email"),
        "phone"           : groq_data.get("phone"),
        "linkedin"        : groq_data.get("linkedin"),
        "github"          : groq_data.get("github"),
        "education"       : groq_data.get("education"),
        "experience_years": exp,
        "current_role"    : groq_data.get("current_role"),
        "skills"          : all_skills,
        "raw_text"        : text
    }