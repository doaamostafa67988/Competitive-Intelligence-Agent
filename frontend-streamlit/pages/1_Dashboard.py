"""Redirect-style page kept for nav symmetry with the Next.js app; the real
dashboard content lives in app.py (Streamlit's home page)."""
import streamlit as st
st.set_page_config(page_title="Dashboard", page_icon="📊")
st.title("📊 Dashboard")
st.info("This is the home page — see the main '📡 Competitive Intel Dashboard' entry in the sidebar.")
