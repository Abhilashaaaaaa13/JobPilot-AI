# backend/utils/ats_scorer.py
# ATS Score — resume vs job description
# Keyword match percentage calculate karo
# Why spaCy?
# Simple split() se "Machine Learning" ek
# word nahi dono alag ho jaate.
# spaCy noun phrases detect karta hai.

import spacy
import re
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# Models load karo — ek baar load hoga
# global scope mein — har call pe reload nahi
try:
    nlp = spacy.load("en_core_web_sm")
except:
    nlp = None
    print("⚠️ spaCy model missing")

# sentence-transformers model
# all-MiniLM-L6-v2 — lightweight, fast, free
# First time download hoga (~80MB)
# Baad mein cache se load hoga
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Common tech skills — better matching ke liye
TECH_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "golang",
    "react", "nextjs", "nodejs", "fastapi", "django", "flask",
    "langchain", "langgraph", "llamaindex", "rag", "llm", "nlp",
    "machine learning", "deep learning", "computer vision",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "sql", "postgresql", "mongodb", "redis", "sqlite", "mysql",
    "chromadb", "pinecone", "weaviate", "vector db", "vector database",
    "docker", "kubernetes", "aws", "gcp", "azure", "linux",
    "rest api", "graphql", "microservices", "system design",
    "data structures", "algorithms", "git", "github",
    "html", "css", "tailwind", "figma", "typescript"
]


def extract_keywords(text: str) -> list:
    """
    Text se tech keywords extract karo.
    
    2 methods:
    1. TECH_SKILLS list se exact match
    2. spaCy se noun phrases (agar available)
    
    Why dono?
    TECH_SKILLS = known terms, reliable
    spaCy = unknown terms bhi catch ho jaate
    """
    text_lower = text.lower()
    found = []

    # Method 1 — known skills list
    for skill in TECH_SKILLS:
        if skill in text_lower:
            found.append(skill)

    # Method 2 — spaCy noun phrases
    if nlp:
        doc = nlp(text)
        for chunk in doc.noun_chunks:
            chunk_text = chunk.text.lower().strip()
            if (len(chunk_text) > 2 and
                chunk_text not in found and
                not chunk_text.isdigit()):
                found.append(chunk_text)

    return list(set(found))


def keyword_match_score(
    user_skills : list,
    jd_keywords : list
) -> float:
    """
    Simple keyword overlap score.
    
    Formula:
    matched / total_required * 100
    
    Example:
    JD needs: Python, ML, LangChain, RAG (4 skills)
    User has: Python, ML, LangChain (3 match)
    Score = 3/4 * 100 = 75%
    """
    if not jd_keywords:
        return 0.0

    user_lower = [s.lower() for s in user_skills]
    jd_lower   = [k.lower() for k in jd_keywords]

    matched = sum(
        1 for skill in jd_lower
        if any(skill in u or u in skill for u in user_lower)
    )

    return round((matched / len(jd_lower)) * 100, 2)


def semantic_similarity_score(
    user_skills_text : str,
    jd_text          : str
) -> float:
    """
    Semantic similarity — embeddings se.
    
    Why ye?
    Keyword match: "ML" nahi milega "Machine Learning" se
    Semantic:      dono similar hain — catch ho jaayenge
    
    Process:
    1. Dono texts ko vectors mein convert karo
    2. Cosine similarity calculate karo
    3. 0 to 1 → multiply by 100
    """
    if not user_skills_text or not jd_text:
        return 0.0

    embeddings = embedder.encode([user_skills_text, jd_text])
    score      = cosine_similarity(
        [embeddings[0]],
        [embeddings[1]]
    )[0][0]

    return round(float(score) * 100, 2)


def calculate_fit_score(
    user_skills     : list,
    experience_years: int,
    job_description : str,
    job_title       : str = ""
) -> dict:
    """
    Final fit score calculate karo.
    
    Weightage:
    → Keyword match:   50%
    → Semantic score:  40%
    → Experience:      10%
    
    Why ye weights?
    Keywords = most important — direct match
    Semantic = context — synonyms catch karo
    Experience = less important for freshers/interns
    """
    # JD se keywords extract karo
    jd_text     = job_title + " " + job_description
    jd_keywords = extract_keywords(jd_text)

    # Keyword score
    kw_score = keyword_match_score(user_skills, jd_keywords)

    # Semantic score
    user_text = " ".join(user_skills)
    sem_score = semantic_similarity_score(user_text, jd_text)

    # Experience score
    # Fresher = 0 years → neutral score
    # Experienced = bonus
    exp_score = min(experience_years * 10, 100)

    # Weighted final score
    final = (
        kw_score  * 0.50 +
        sem_score * 0.40 +
        exp_score * 0.10
    )
    final = round(final, 2)

    return {
        "fit_score"       : int(final),
        "keyword_score"   : kw_score,
        "semantic_score"  : sem_score,
        "experience_score": exp_score,
        "matched_keywords": [
            k for k in jd_keywords
            if any(k in u.lower() or u.lower() in k
                   for u in user_skills)
        ],
        "missing_keywords": [
            k for k in jd_keywords
            if not any(k in u.lower() or u.lower() in k
                       for u in user_skills)
        ],
        "is_relevant"     : final >= 50
    }


def calculate_ats_score(
    resume_text     : str,
    job_description : str
) -> dict:
    """
    ATS Score — resume vs job description.
    Resume Agent is score ko use karega
    resume rewrite karne ke liye.
    
    Same logic as fit score but:
    → resume text vs JD
    → missing keywords = resume mein add karne hain
    """
    jd_keywords     = extract_keywords(job_description)
    resume_keywords = extract_keywords(resume_text)

    resume_lower = [k.lower() for k in resume_keywords]
    matched = [
        k for k in jd_keywords
        if any(k in r or r in k for r in resume_lower)
    ]
    missing = [
        k for k in jd_keywords
        if not any(k in r or r in k for r in resume_lower)
    ]

    score = round(len(matched) / len(jd_keywords) * 100, 2) if jd_keywords else 0

    return {
        "ats_score"        : int(score),
        "matched_keywords" : matched,
        "missing_keywords" : missing,
        "total_jd_keywords": len(jd_keywords)
    }