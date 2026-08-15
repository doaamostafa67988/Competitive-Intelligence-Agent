"""
Manage the list of tracked competitors and their source URLs (pricing page,
careers page). These feed the Research Agent on the next pipeline run.
"""
import streamlit as st
import api_client as api

st.set_page_config(page_title="Competitors", page_icon="🏢", layout="wide")
st.title("🏢 Tracked Competitors")

st.subheader("Discover competitors")
st.caption("Enter your own company — this searches the web and suggests real competitors instead of typing each one by hand.")
with st.form("discover_competitors"):
    own_company = st.text_input("Your company name*")
    discover_submitted = st.form_submit_button("Discover")
    if discover_submitted:
        if not own_company:
            st.error("Enter your company name.")
        else:
            with st.spinner(f"Searching the web for {own_company}'s competitors…"):
                try:
                    st.session_state["suggestions"] = api.discover_competitors(own_company)
                    if not st.session_state["suggestions"]:
                        st.warning("No suggestions found. You can still add competitors manually below.")
                except Exception as e:
                    st.error(f"Discovery failed: {e}")

suggestions = st.session_state.get("suggestions")
if suggestions:
    st.write("**Suggested competitors** — pick the ones to start tracking:")
    for s in suggestions:
        col_name, col_reason, col_add = st.columns([2, 4, 1])
        col_name.write(f"**{s['name']}**")
        col_reason.caption(s.get("reason", ""))
        if col_add.button("Add", key=f"add_{s['name']}"):
            try:
                api.upsert_competitor(s["name"], None, None)
                st.success(f"Added {s['name']}.")
                st.session_state["suggestions"] = [x for x in suggestions if x["name"] != s["name"]]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add: {e}")

st.divider()

with st.form("add_competitor"):
    st.subheader("Add / update a competitor")
    name = st.text_input("Competitor name*")
    pricing_url = st.text_input("Pricing page URL")
    careers_url = st.text_input("Careers page URL")
    submitted = st.form_submit_button("Save")
    if submitted:
        if not name:
            st.error("Competitor name is required.")
        else:
            try:
                api.upsert_competitor(name, pricing_url or None, careers_url or None)
                st.success(f"Saved {name}.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

st.divider()
st.subheader("Currently tracked")
try:
    competitors = api.list_competitors()
    if competitors:
        for c in competitors:
            col_name, col_pricing, col_careers, col_remove = st.columns([2, 3, 3, 1])
            col_name.write(f"**{c.get('name')}**")
            col_pricing.write(c.get("pricing_url") or "—")
            col_careers.write(c.get("careers_url") or "—")
            if col_remove.button("Remove", key=f"remove_{c.get('name')}"):
                try:
                    api.remove_competitor(c["name"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to remove: {e}")
    else:
        st.info("No competitors added yet.")
except Exception as e:
    st.warning(f"Could not reach backend: {e}")
