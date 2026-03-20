# Pehle — requests se API call
# Ab — direct DB call
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import streamlit as st
from backend.database import SessionLocal
from backend.models.user import User
from backend.utils.auth_utils import (
    hash_password,
    verify_password
)

def register_user(email: str, password: str) -> tuple:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(
            User.email == email
        ).first()
        if existing:
            return False, "Email already registered"

        user = User(
            email           = email,
            hashed_password = hash_password(password)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return True, user
    except Exception as e:
        db.rollback()
        return False, str(e)
    finally:
        db.close()


def login_user(email: str, password: str) -> tuple:
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.email == email
        ).first()

        if not user or not verify_password(
            password, user.hashed_password
        ):
            return False, "Invalid email or password"

        if not user.is_active:
            return False, "Account inactive"

        return True, user
    except Exception as e:
        return False, str(e)
    finally:
        db.close()


# ── UI ────────────────────────────────────────
st.title("🤖 Job Hunter Agent")

tab1, tab2 = st.tabs(["Login", "Register"])

with tab2:
    st.subheader("Create Account")
    reg_email = st.text_input("Email",    key="reg_email")
    reg_pass  = st.text_input("Password", key="reg_pass",
                               type="password")

    if st.button("Register"):
        if not reg_email or not reg_pass:
            st.error("Email aur password daalo")
        else:
            success, result = register_user(reg_email, reg_pass)
            if success:
                st.success("✅ Account created — ab login karo")
            else:
                st.error(result)

with tab1:
    st.subheader("Login")
    login_email = st.text_input("Email",    key="login_email")
    login_pass  = st.text_input("Password", key="login_pass",
                                 type="password")

    if st.button("Login"):
        if not login_email or not login_pass:
            st.error("Email aur password daalo")
        else:
            success, result = login_user(login_email, login_pass)
            if success:
                st.session_state["user_id"] = result.id
                st.session_state["email"]   = result.email
                st.success("✅ Login successful!")
                st.switch_page("pages/2_onboarding.py")
            else:
                st.error(result)