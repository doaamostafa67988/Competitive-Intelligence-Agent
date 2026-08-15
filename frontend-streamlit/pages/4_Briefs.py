"""
Full brief history browser: pick a past weekly brief and read the formatted
executive summary, sections, change log, and flagged unconfirmed claims.
"""
import streamlit as st
import api_client as api

st.set_page_config(page_title="Briefs", page_icon="📰", layout="wide")
st.title("📰 Brief History")

try:
    briefs = api.list_briefs(limit=50)
except Exception as e:
    st.warning(f"Could not reach backend: {e}")
    briefs = []

if not briefs:
    st.info("No briefs yet — run the pipeline from the Dashboard.")
else:
    options = {f"{b['run_date']} — {', '.join(b['competitors_covered'])}": b["id"] for b in briefs}
    choice = st.selectbox("Select a brief", list(options.keys()))
    brief_id = options[choice]

    detail = api.get_brief(brief_id)

    st.header("Executive Summary")
    st.write(detail["executive_summary"])

    for section in detail["sections"]:
        st.subheader(section["heading"])
        st.markdown(section["body_markdown"])
        if section.get("cited_source_urls"):
            st.caption("Sources: " + ", ".join(section["cited_source_urls"]))

    if detail["change_log"]:
        st.subheader("🆕 What's New This Week")
        for entry in detail["change_log"]:
            icon = {"new": "🟢", "modified": "🟡", "removed": "🔴"}.get(entry["change_type"], "⚪")
            st.markdown(f"{icon} **{entry['competitor']}** — {entry['description']}")

    if detail["unconfirmed_claims"]:
        st.subheader("⚠️ Unconfirmed (flagged, excluded from headline claims)")
        for c in detail["unconfirmed_claims"]:
            st.markdown(f"- {c}")

    st.divider()
    md = api.get_brief_markdown(brief_id)
    st.download_button("⬇ Download as Markdown", md, file_name=f"brief_{brief_id}.md")
