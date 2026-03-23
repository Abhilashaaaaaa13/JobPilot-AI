# backend/agents/apply_agent.py
# Playwright se portals pe auto-fill aur apply

import os
import asyncio
from loguru import logger
from dotenv import load_dotenv
load_dotenv()

HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"


# ─────────────────────────────────────────────
# USER PROFILE FETCH
# ─────────────────────────────────────────────

def get_user_profile(user_id: int) -> dict:
    """DB se user ka poora profile lo."""
    try:
        from backend.database    import SessionLocal
        from backend.models.user import UserProfile, User

        db      = SessionLocal()
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        user    = db.query(User).filter(
            User.id == user_id
        ).first()
        db.close()

        if not profile or not user:
            return {}

        import json
        skills = []
        try:
            skills = json.loads(profile.skills) if profile.skills else []
        except:
            pass

        return {
            "name"            : profile.full_name     or "",
            "email"           : user.email            or "",
            "phone"           : profile.phone         or "",
            "college"         : profile.college       or "",
            "degree"          : profile.degree        or "",
            "graduation_year" : str(profile.graduation_year or ""),
            "cgpa"            : str(profile.cgpa      or ""),
            "skills"          : ", ".join(skills),
            "linkedin"        : profile.linkedin_url  or "",
            "github"          : profile.github_url    or "",
            "portfolio"       : profile.portfolio_url or "",
            "experience_years": str(profile.experience_years or "0"),
            "resume_path"     : f"uploads/{user_id}/resume_base.pdf",
        }
    except Exception as e:
        logger.error(f"Profile fetch error: {e}")
        return {}


# ─────────────────────────────────────────────
# INTERNSHALA APPLY
# ─────────────────────────────────────────────

async def apply_internshala(page, profile: dict, job_url: str) -> dict:
    """Internshala pe apply karo."""
    try:
        await page.goto(job_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Login check — agar login page aaye
        if "login" in page.url or "signin" in page.url:
            # Email/password fill karo
            email_sel = 'input[type="email"], input[name="email"]'
            pass_sel  = 'input[type="password"]'

            if await page.locator(email_sel).count() > 0:
                await page.fill(email_sel, profile["email"])
                await page.fill(pass_sel,  "")   # Password user ne set kiya hoga
                logger.warning("Internshala login required — password nahi hai")
                return {"success": False, "error": "Login required — password nahi hai profile mein"}

        # Apply button dhundho
        apply_btn = page.locator(
            'button:has-text("Apply"), a:has-text("Apply now"), '
            'button:has-text("Apply now"), .apply-button'
        ).first

        if await apply_btn.count() == 0:
            return {"success": False, "error": "Apply button nahi mila"}

        await apply_btn.click()
        await page.wait_for_timeout(2000)

        # Cover letter / availability form
        cover_letter_sel = 'textarea[name*="cover"], textarea[placeholder*="cover"], textarea[placeholder*="why"]'
        if await page.locator(cover_letter_sel).count() > 0:
            await page.fill(
                cover_letter_sel,
                f"I am {profile['name']}, a {profile['degree']} student from {profile['college']}. "
                f"I have skills in {profile['skills'][:200]}. "
                f"I am eager to contribute to your team."
            )

        # Availability
        avail_sel = 'input[name*="availability"], input[placeholder*="availability"]'
        if await page.locator(avail_sel).count() > 0:
            await page.fill(avail_sel, "Immediately")

        # Submit
        submit_btn = page.locator(
            'button[type="submit"]:has-text("Submit"), '
            'button:has-text("Submit application"), '
            'button:has-text("Apply")'
        ).first

        if await submit_btn.count() > 0:
            await submit_btn.click()
            await page.wait_for_timeout(3000)

        logger.info(f"✅ Internshala apply done: {job_url}")
        return {"success": True, "portal": "internshala", "url": page.url}

    except Exception as e:
        logger.error(f"Internshala apply error: {e}")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# UNSTOP APPLY
# ─────────────────────────────────────────────

async def apply_unstop(page, profile: dict, job_url: str) -> dict:
    """Unstop pe apply karo."""
    try:
        await page.goto(job_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Apply button
        apply_btn = page.locator(
            'button:has-text("Apply"), button:has-text("Register"), '
            'a:has-text("Apply now")'
        ).first

        if await apply_btn.count() == 0:
            return {"success": False, "error": "Apply button nahi mila"}

        await apply_btn.click()
        await page.wait_for_timeout(2000)

        # Form fields fill karo
        fields = {
            'input[name*="name"], input[placeholder*="name"]'        : profile["name"],
            'input[name*="email"], input[type="email"]'               : profile["email"],
            'input[name*="phone"], input[placeholder*="phone"]'       : profile["phone"],
            'input[name*="college"], input[placeholder*="college"]'   : profile["college"],
            'input[name*="cgpa"], input[placeholder*="cgpa"]'         : profile["cgpa"],
            'input[name*="linkedin"], input[placeholder*="linkedin"]' : profile["linkedin"],
            'input[name*="github"], input[placeholder*="github"]'     : profile["github"],
        }

        for selector, value in fields.items():
            if value and await page.locator(selector).count() > 0:
                await page.fill(selector, value)
                await page.wait_for_timeout(300)

        # Resume upload
        resume_input = page.locator('input[type="file"]').first
        if await resume_input.count() > 0 and os.path.exists(profile["resume_path"]):
            await resume_input.set_input_files(profile["resume_path"])
            await page.wait_for_timeout(1000)

        # Submit
        submit_btn = page.locator(
            'button[type="submit"], button:has-text("Submit"), '
            'button:has-text("Apply")'
        ).last

        if await submit_btn.count() > 0:
            await submit_btn.click()
            await page.wait_for_timeout(3000)

        logger.info(f"✅ Unstop apply done: {job_url}")
        return {"success": True, "portal": "unstop", "url": page.url}

    except Exception as e:
        logger.error(f"Unstop apply error: {e}")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# REMOTIVE APPLY
# ─────────────────────────────────────────────

async def apply_remotive(page, profile: dict, job_url: str) -> dict:
    """
    Remotive jobs mostly company ke apne portal pe redirect karti hain.
    Wahan jaake apply karo.
    """
    try:
        await page.goto(job_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Remotive pe "Apply for this job" button company URL pe le jaata hai
        apply_link = page.locator(
            'a:has-text("Apply for this job"), '
            'a:has-text("Apply now"), '
            'a.apply-link'
        ).first

        if await apply_link.count() == 0:
            return {"success": False, "error": "Apply link nahi mila Remotive pe"}

        # Company portal URL lo
        company_url = await apply_link.get_attribute("href")
        if not company_url:
            await apply_link.click()
            await page.wait_for_timeout(2000)
            company_url = page.url

        # Company portal pe jaao
        await page.goto(company_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Generic form fill
        result = await apply_generic(page, profile, company_url)
        result["portal"] = "remotive"
        return result

    except Exception as e:
        logger.error(f"Remotive apply error: {e}")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# YC JOBS (WorkAtAStartup) APPLY
# ─────────────────────────────────────────────

async def apply_yc(page, profile: dict, job_url: str) -> dict:
    """YC / WorkAtAStartup pe apply karo."""
    try:
        await page.goto(job_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Apply button
        apply_btn = page.locator(
            'a:has-text("Apply"), button:has-text("Apply"), '
            'a:has-text("Apply to")'
        ).first

        if await apply_btn.count() == 0:
            # Seedha company website pe redirect ho sakta hai
            return await apply_generic(page, profile, job_url)

        await apply_btn.click()
        await page.wait_for_timeout(2000)

        # Form fill
        fields = {
            'input[name*="name"]'      : profile["name"],
            'input[name*="email"]'     : profile["email"],
            'input[name*="phone"]'     : profile["phone"],
            'input[name*="linkedin"]'  : profile["linkedin"],
            'input[name*="github"]'    : profile["github"],
            'input[name*="portfolio"]' : profile["portfolio"],
        }

        for selector, value in fields.items():
            if value and await page.locator(selector).count() > 0:
                await page.fill(selector, value)
                await page.wait_for_timeout(300)

        # Why join textarea
        why_sel = 'textarea[name*="why"], textarea[placeholder*="why"], textarea[name*="cover"]'
        if await page.locator(why_sel).count() > 0:
            await page.fill(
                why_sel,
                f"I'm {profile['name']} with {profile['experience_years']} years of experience. "
                f"My skills include {profile['skills'][:200]}. "
                f"I'm excited about this opportunity."
            )

        # Resume upload
        resume_input = page.locator('input[type="file"]').first
        if await resume_input.count() > 0 and os.path.exists(profile["resume_path"]):
            await resume_input.set_input_files(profile["resume_path"])
            await page.wait_for_timeout(1000)

        # Submit
        submit_btn = page.locator(
            'button[type="submit"], button:has-text("Submit")'
        ).last
        if await submit_btn.count() > 0:
            await submit_btn.click()
            await page.wait_for_timeout(3000)

        logger.info(f"✅ YC apply done: {job_url}")
        return {"success": True, "portal": "yc_jobs", "url": page.url}

    except Exception as e:
        logger.error(f"YC apply error: {e}")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# GENERIC APPLY (fallback)
# ─────────────────────────────────────────────

async def apply_generic(page, profile: dict, job_url: str) -> dict:
    """Generic form fill — kisi bhi portal ke liye fallback."""
    try:
        # Common field selectors
        fields = {
            'input[name*="first_name"], input[placeholder*="first name"]': profile["name"].split()[0] if profile["name"] else "",
            'input[name*="last_name"],  input[placeholder*="last name"]' : profile["name"].split()[-1] if profile["name"] else "",
            'input[name*="full_name"],  input[placeholder*="full name"]' : profile["name"],
            'input[name*="name"]:not([name*="company"])' : profile["name"],
            'input[type="email"]'                        : profile["email"],
            'input[name*="phone"], input[type="tel"]'    : profile["phone"],
            'input[name*="college"], input[name*="university"]': profile["college"],
            'input[name*="linkedin"]'                    : profile["linkedin"],
            'input[name*="github"]'                      : profile["github"],
            'input[name*="portfolio"], input[name*="website"]': profile["portfolio"],
        }

        for selector, value in fields.items():
            if not value:
                continue
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0:
                    await loc.fill(value)
                    await page.wait_for_timeout(200)
            except:
                continue

        # Resume upload
        resume_input = page.locator('input[type="file"]').first
        if await resume_input.count() > 0 and os.path.exists(profile["resume_path"]):
            await resume_input.set_input_files(profile["resume_path"])
            await page.wait_for_timeout(1000)

        # Submit
        submit_btn = page.locator(
            'button[type="submit"], button:has-text("Submit"), '
            'button:has-text("Apply"), input[type="submit"]'
        ).last
        if await submit_btn.count() > 0:
            await submit_btn.click()
            await page.wait_for_timeout(3000)

        return {"success": True, "portal": "generic", "url": page.url}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def apply_to_job(
    user_id     : int,
    job_url     : str,
    source      : str,
    resume_path : str = None
) -> dict:
    """
    Sync wrapper — Streamlit se call karo.

    Args:
        user_id    : int
        job_url    : job ka URL
        source     : "internshala" | "unstop" | "remotive" | "yc_jobs"
        resume_path: optimized ya original resume path
    """
    return asyncio.run(
        _apply_async(user_id, job_url, source, resume_path)
    )


async def _apply_async(
    user_id     : int,
    job_url     : str,
    source      : str,
    resume_path : str = None
) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error"  : "Playwright install nahi hai — `pip install playwright && playwright install chromium`"
        }

    profile = get_user_profile(user_id)
    if not profile:
        return {"success": False, "error": "User profile nahi mila"}

    # Resume path override
    if resume_path:
        profile["resume_path"] = resume_path

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            accept_downloads = True,
            viewport         = {"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            if source == "internshala":
                result = await apply_internshala(page, profile, job_url)
            elif source == "unstop":
                result = await apply_unstop(page, profile, job_url)
            elif source == "remotive":
                result = await apply_remotive(page, profile, job_url)
            elif source == "yc_jobs":
                result = await apply_yc(page, profile, job_url)
            else:
                result = await apply_generic(page, profile, job_url)

            # Screenshot le lo proof ke liye
            screenshot_dir  = f"uploads/{user_id}/screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = f"{screenshot_dir}/{source}_{hash(job_url)}.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            result["screenshot"] = screenshot_path

        except Exception as e:
            result = {"success": False, "error": str(e)}
        finally:
            await browser.close()

    return result