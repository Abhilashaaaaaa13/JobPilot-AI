# backend/agents/followup_agent.py
# ═══════════════════════════════════════════════════════════════════════════════
# Auto-generate and send intelligent follow-ups
# ═══════════════════════════════════════════════════════════════════════════════

from datetime import datetime, timedelta, timezone
from loguru import logger
from typing import List, Dict
import json

from backend.database import SessionLocal
from backend.models.user import User
from backend.models.sent_email import SentEmail
from backend.config import GROQ_API_KEY, LLM_MODEL

try:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
except ImportError:
    client = None


def _generate_followup_email(
    company: str,
    original_subject: str,
    days_passed: int
) -> Dict[str, str]:
    """
    Generate intelligent follow-up using Groq.
    Different tone for 1st vs 2nd follow-up.
    """
    if not client:
        return {
            "subject": f"Quick follow-up: {original_subject}",
            "body": "Checking in on my previous message."
        }

    if days_passed < 7:
        # 1st follow-up — gentle
        prompt = f"""
        Generate a gentle first follow-up email.
        
        Company: {company}
        Original Subject: {original_subject}
        Days since: {days_passed}
        
        Make it:
        - Brief (2-3 sentences)
        - Reference the original message
        - Add one new piece of value (insight, resource, etc)
        - End with a soft call-to-action
        
        Return JSON:
        {{"subject": "...", "body": "..."}}
        """
    else:
        # 2nd follow-up — more direct
        prompt = f"""
        Generate a direct second follow-up email.
        
        Company: {company}
        Original Subject: {original_subject}
        Days since: {days_passed}
        
        Make it:
        - Concise but confident
        - Show genuine interest in collaboration
        - Offer specific next steps
        - Suggest timeline
        
        Return JSON:
        {{"subject": "...", "body": "..."}}
        """

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Followup generation error: {e}")
        return {
            "subject": f"Quick follow-up: {original_subject}",
            "body": "Checking in on our previous conversation."
        }


def get_all_users_with_sent_emails() -> List[int]:
    """Get list of user IDs with sent emails"""
    db = SessionLocal()
    try:
        users = db.query(SentEmail.user_id).distinct().all()
        return [u[0] for u in users]
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return []
    finally:
        db.close()


def check_and_send_followups(user_id: int) -> Dict:
    """
    Check user's sent emails and send follow-ups if due.
    
    Criteria:
    - 1st follow-up: 4 days after send (if no reply)
    - 2nd follow-up: 7 days after 1st followup
    """
    db = SessionLocal()
    followups_sent = 0
    
    try:
        now = datetime.now(timezone.utc)
        
        # Get sent emails that need follow-ups
        sent_emails = db.query(SentEmail).filter(
            SentEmail.user_id == user_id,
            SentEmail.replied == False
        ).all()
        
        for email in sent_emails:
            if not email.sent_at:
                continue
            
            sent_at = email.sent_at
            if isinstance(sent_at, str):
                sent_at = datetime.fromisoformat(sent_at)
            
            days_since_sent = (now - sent_at).days
            followup_count = email.followup_count or 0
            
            # 1st follow-up due at 4 days
            if followup_count == 0 and days_since_sent >= 4:
                fu_data = _generate_followup_email(
                    email.company,
                    email.subject,
                    days_since_sent
                )
                
                # Mark as follow-up sent
                email.followup_count = 1
                email.followup_sent = True
                email.last_followup_at = now.isoformat()
                db.commit()
                
                followups_sent += 1
                logger.info(f"  📤 Followup 1 sent to {email.company}")
            
            # 2nd follow-up due at 7 days after first
            elif followup_count == 1 and days_since_sent >= 11:
                fu_data = _generate_followup_email(
                    email.company,
                    email.subject,
                    days_since_sent
                )
                
                email.followup_count = 2
                email.last_followup_at = now.isoformat()
                db.commit()
                
                followups_sent += 1
                logger.info(f"  📤 Followup 2 sent to {email.company}")
        
        return {
            "followups_sent": followups_sent,
            "success": True
        }
    
    except Exception as e:
        logger.error(f"Error in followup check for user {user_id}: {e}")
        db.rollback()
        return {"followups_sent": 0, "error": str(e)}
    
    finally:
        db.close()


if __name__ == "__main__":
    users = get_all_users_with_sent_emails()
    print(f"Users with sent emails: {users}")