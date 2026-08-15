"""
Streamlit entrypoint: overview dashboard for the Competitive Intelligence &
Market Watch Agent. Run with:  streamlit run app.py
"""
import streamlit as st
from datetime import date, timedelta
import api_client as api

st.set_page_config(page_title="Competitive Intel Dashboard", page_icon="📡", layout="wide")

st.title("📡 Competitive Intelligence & Market Watch")
st.caption("Standing multi-agent system tracking competitor pricing, announcements, and hiring signals.")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Run the pipeline")
    publish = st.checkbox("Publish result to Telegram", value=False)
    if st.button("▶ Run weekly pipeline now", type="primary"):
        with st.spinner("Research → Fact-Check → Graph-Build → Analyze → Change-Log ..."):
            try:
                # Use whatever is configured on the Competitors page, if any.
                # Falling back to None lets the backend use TRACKED_COMPETITORS
                # from .env when nothing has been added yet.
                configured = api.list_competitors()
                targets = configured if configured else None
                brief = api.run_pipeline(targets=targets, publish_to_telegram_chat=publish)
                st.success(f"Brief generated: {brief['id']}")
            except Exception as e:
                st.error(f"Pipeline run failed: {e}")

with col2:
    st.subheader("Repeat price changers")
    since = (date.today() - timedelta(days=90)).isoformat()
    try:
        rows = api.repeat_price_changers(since=since, n=2)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No competitor has changed pricing 2+ times in the last 90 days.")
    except Exception as e:
        st.warning(f"Could not reach backend: {e}")

with col3:
    st.subheader("Tracked competitors")
    try:
        competitors = api.list_competitors()
        if competitors:
            for c in competitors:
                st.markdown(f"- **{c.get('name')}**")
        else:
            st.info("No competitors configured yet — add one on the Competitors page.")
    except Exception as e:
        st.warning(f"Could not reach backend: {e}")

st.divider()
st.subheader("Latest briefs")
try:
    briefs = api.list_briefs(limit=5)
    if not briefs:
        st.info("No briefs generated yet. Run the pipeline above to produce the first one.")
    for b in briefs:
        with st.expander(f"{b['run_date']} — {', '.join(b['competitors_covered'])}"):
            st.write(b["executive_summary"])
            st.page_link("pages/4_Briefs.py", label="Open full brief →")
except Exception as e:
    st.warning(f"Could not reach backend: {e}")

st.divider()
st.caption("Use the sidebar to explore Competitors, the Knowledge Graph, and full Brief history.")
