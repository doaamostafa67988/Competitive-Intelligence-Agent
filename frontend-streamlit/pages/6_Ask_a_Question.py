"""
Ask an arbitrary free-text question about tracked competitors. Unlike the
weekly Brief (fixed sections, same query shape every run), this hands the
question to the Q&A Agent, which decides on its own whether to run a
semantic search over announcements/press-releases/job-postings or a graph
lookup for pricing patterns - see backend/app/agents/qa_agent.py.
"""
import streamlit as st
import api_client as api

st.set_page_config(page_title="Ask a Question", page_icon="💬", layout="wide")
st.title("💬 Ask About Competitors")
st.caption(
    "The agent decides on the fly which lookup answers your question - a semantic search over "
    "announcements, a graph query for pricing patterns, both, or neither if the question doesn't need one."
)

EXAMPLES = [
    "Which competitors have changed their pricing more than once recently?",
    "Is anyone talking about AI features in their announcements?",
    "What has Acme Corp announced lately?",
]

cols = st.columns(len(EXAMPLES))
clicked_example = None
for col, example in zip(cols, EXAMPLES):
    if col.button(example, use_container_width=True):
        clicked_example = example

with st.form("ask_question"):
    question = st.text_area(
        "Your question",
        value=clicked_example or st.session_state.get("qa_last_question", ""),
        placeholder="e.g. Which competitors raised prices twice this quarter?",
        height=90,
    )
    submitted = st.form_submit_button("Ask")

if submitted and question.strip():
    st.session_state["qa_last_question"] = question.strip()
    with st.spinner("Thinking…"):
        try:
            st.session_state["qa_last_result"] = api.ask_question(question.strip())
        except Exception as e:
            st.error(f"Failed to get an answer: {e}")
            st.session_state["qa_last_result"] = None
elif submitted:
    st.error("Enter a question first.")

result = st.session_state.get("qa_last_result")
if result:
    st.divider()
    st.write(result["answer"])
    if result.get("tools_used"):
        st.caption("Lookups used: " + ", ".join(f"`{t}`" for t in result["tools_used"]))
    else:
        st.caption("No data lookup was needed to answer this.")
    if result.get("sources"):
        with st.expander("Sources used"):
            for s in result["sources"]:
                label = s.get("competitor") or "—"
                url = s.get("source_url")
                st.markdown(f"- **{label}**: {url}" if url else f"- **{label}**: no link")

st.divider()
st.subheader("Tracked Topics")
st.caption(
    "Drives the weekly brief's \"Thematic Trends\" section and the \"What's New\" summary — "
    "add whatever you actually want watched instead of the default set."
)

try:
    topics = api.list_topics()
except Exception as e:
    topics = []
    st.error(f"Failed to load topics: {e}")

with st.form("add_topic", clear_on_submit=True):
    new_topic = st.text_input("New topic", placeholder="e.g. layoffs, enterprise pricing, EU expansion")
    if st.form_submit_button("Add topic") and new_topic.strip():
        try:
            api.add_topic(new_topic.strip())
            st.rerun()
        except Exception as e:
            st.error(f"Failed to add topic: {e}")

if not topics:
    st.caption("No topics yet — the brief falls back to a default set (AI features, enterprise expansion, new integrations).")
else:
    for t in topics:
        col1, col2 = st.columns([5, 1])
        col1.write(t["topic"])
        if col2.button("Remove", key=f"remove_{t['id']}"):
            api.remove_topic(t["id"])
            st.rerun()
