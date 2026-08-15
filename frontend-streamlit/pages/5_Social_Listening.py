"""
Ad-hoc social listening scan: enter up to 5 competitor names, scan
Twitter/X, LinkedIn, and Reddit via SerpAPI, and see tone/voice, pricing
clarity, hiring signal, social momentum, and content velocity each scored
1-10 with a short rationale. Separate from the weekly pipeline - this is
for quick lookups, not the scheduled knowledge-graph brief.
"""
import streamlit as st
import api_client as api

st.set_page_config(page_title="Social Listening", page_icon="📡", layout="wide")
st.title("📡 Social Listening")
st.caption("Scan up to 5 competitors across Twitter/X, LinkedIn, and Reddit.")

DIMENSIONS = [
    ("tone_voice", "Tone & Voice"),
    ("pricing_clarity", "Pricing Clarity"),
    ("hiring_signal", "Hiring Signal"),
    ("social_momentum", "Social Momentum"),
    ("content_velocity", "Content Velocity"),
]

PLATFORM_OPTIONS = {"Twitter/X": "twitter", "LinkedIn": "linkedin", "Reddit": "reddit"}

with st.form("social_scan"):
    names_raw = st.text_area(
        "Competitor names (one per line, up to 5)",
        placeholder="Acme Corp\nBeta Analytics\nCirrus AI",
        height=110,
    )
    selected_platforms = st.multiselect(
        "Platforms", list(PLATFORM_OPTIONS.keys()), default=list(PLATFORM_OPTIONS.keys())
    )
    submitted = st.form_submit_button("Scan")

if submitted:
    competitors = [n.strip() for n in names_raw.splitlines() if n.strip()][:5]
    if not competitors:
        st.error("Enter at least one competitor name.")
    else:
        platforms = [PLATFORM_OPTIONS[p] for p in selected_platforms] or None
        with st.spinner(f"Scanning {len(competitors)} competitor(s)…"):
            try:
                st.session_state["last_scorecards"] = api.social_scan(competitors, platforms)
            except Exception as e:
                st.error(f"Scan failed: {e}")

scorecards = st.session_state.get("last_scorecards")
if scorecards:
    for card in scorecards:
        st.divider()
        st.subheader(card["competitor"])
        covered = ", ".join(card.get("platforms_covered", [])) or "none found"
        st.caption(f"Scanned {card['scanned_at']} · platforms with data: {covered}")
        st.write(card["overall_summary"])

        cols = st.columns(5)
        for col, (key, label) in zip(cols, DIMENSIONS):
            dim = card[key]
            col.metric(label, f"{dim['score']}/10", dim["label"])
            col.caption(dim["rationale"])

        if card.get("sample_posts"):
            with st.expander(f"Sample posts ({len(card['sample_posts'])})"):
                for p in card["sample_posts"]:
                    label = p["title"] or p["url"]
                    st.markdown(f"**[{p['platform']}]** [{label}]({p['url']})  \n{p['snippet']}")
else:
    st.info("Enter competitor names above and click Scan to see results.")
