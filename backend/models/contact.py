# backend/models/contact.py
# Contact — CEO/CTO/HR per company
# Why separate table?
# Ek company ke multiple contacts ho sakte hain
# Founder ko alag email, HR ko alag email

from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"))

    name = Column(String(200))
    role = Column(String(100))
    email = Column(String(200))
    linkdin_url = Column(String(300))

    confidence_score = Column(Float,default=0.0)
    # 0.0 to 1.0
    # 1.0 = SMTP verified
    # 0.7 = pattern guess, not verified
    # 0.4 = found on website but unsure
    source = Column(String(100))
    # "smtp_verify" / "website" / "hunter" / "pattern_guess"
    priority = Column(Integer, default=5)
    # 1 = Founder (best), 7 = Recruiter (worst)
    # config.py ke CONTACT_PRIORITY se set hoga

    #relationship
    company = relationship("Company", back_populates="contacts")
    