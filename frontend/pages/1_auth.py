# frontend/pages/1_auth.py

import streamlit as st
import requests

API = "http://localhost:8000"

st.title("🤖 Job Hunter Agent")

tab1, tab2 = st.tabs(["Login", "Register"])

# ── Register ──────────────────────────────────
with tab2:
    st.subheader("Create Account")
    email    = st.text_input("Email",    key="reg_email")
    password = st.text_input("Password", key="reg_pass", type="password")

    if st.button("Register"):
        res = requests.post(f"{API}/auth/register", json={
            "email"   : email,
            "password": password
        })
        if res.status_code == 200:
            st.success(" Account created — ab login karo")
        else:
            st.error(res.json().get("detail", "Error"))

# ── Login ─────────────────────────────────────
with tab1:
    st.subheader("Login")
    email    = st.text_input("Email",    key="login_email")
    password = st.text_input("Password", key="login_pass", type="password")

    if st.button("Login"):
        res = requests.post(f"{API}/auth/login", json={
            "email"   : email,
            "password": password
        })
        if res.status_code == 200:
            data = res.json()
            # Session state mein save karo
            # Why session_state?
            # Streamlit har interaction pe rerun hota hai
            # session_state values persist karti hain
            st.session_state["token"]   = data["access_token"]
            st.session_state["user_id"] = data["user_id"]
            st.session_state["email"]   = data["email"]
            st.success(" Login successful")
            st.switch_page("pages/2_onboarding.py")
        else:
            st.error("Invalid email or password")