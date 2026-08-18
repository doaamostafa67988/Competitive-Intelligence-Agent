"""
LangSmith evaluation for each agent in the pipeline.

Run with:
    cd backend && python -m app.eval.run_evals [agent_name ...]
    # e.g. python -m app.eval.run_evals research fact_checker
    # with no args, runs every agent's eval.

Requires LANGCHAIN_API_KEY set (config.py / .env) - each run below
creates/reuses a LangSmith dataset named "<agent>_eval" and uploads an
experiment with per-example scores to LANGCHAIN_PROJECT, viewable in the
LangSmith UI (Datasets & Testing). Without a key this exits early per
agent with a clear message rather than failing confusingly deep inside the
SDK.

Evaluators here are deterministic/structural checks, not an LLM-as-judge -
same reasoning as guardrails.py: a judge call would double LLM cost/latency
for every eval example, and these agents' actual failure modes (bad JSON,
disallowed labels, hallucinated observation ids, ungrounded answers) are
all checkable without one. This intentionally does NOT re-grade content
quality/writing style - only structural correctness and groundedness.
"""
from __future__ import annotations
import sys
from datetime import date
from app.config import get_settings

settings = get_settings()


def _require_langsmith():
    if not settings.LANGCHAIN_API_KEY:
        print("Skipping: LANGCHAIN_API_KEY is not set in .env - no LangSmith project to write results to.")
        return None
    from langsmith import Client
    return Client()


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------

RESEARCH_EXAMPLES = [
    {
        "inputs": {
            "competitor": "Acme Corp",
            "source_type": "news_article",
            "source_url": "https://example.com/acme-raises-prices",
            "raw_text": "Acme Corp announced today it is raising the price of its Pro plan "
            "from $49/month to $59/month, effective next quarter, citing increased infrastructure costs.",
        },
    },
    {
        "inputs": {
            "competitor": "Beta Analytics",
            "source_type": "pricing_page",
            "source_url": "https://beta-analytics.example.com/pricing",
            "raw_text": "404 Not Found. The page you requested could not be located on this server.",
        },
    },
]


def eval_research_source_url_fidelity(run, example) -> dict:
    """Every extracted observation's source_url should trace back to the
    source_url that was actually fed in - catches the LLM inventing or
    swapping a source, which would break the fact-checker's source-count
    logic downstream."""
    expected_url = example.inputs["source_url"]
    observations = run.outputs.get("observations", []) if run.outputs else []
    if not observations:
        return {"key": "source_url_fidelity", "score": 1.0}  # nothing extracted, nothing to be wrong about
    ok = all(o.get("source_url") == expected_url for o in observations)
    return {"key": "source_url_fidelity", "score": 1.0 if ok else 0.0}


def eval_research_skips_garbage(run, example) -> dict:
    """The 404/empty-page example should yield zero observations (input
    guardrail: check_contextual_compliance) - a non-empty result here means
    the LLM hallucinated a fact from a page that had no real content."""
    if "404" not in example.inputs["raw_text"] and "Not Found" not in example.inputs["raw_text"]:
        return {"key": "skips_garbage", "score": 1.0}  # not a garbage-input example, N/A
    observations = run.outputs.get("observations", []) if run.outputs else []
    return {"key": "skips_garbage", "score": 1.0 if not observations else 0.0}


async def _research_target(inputs: dict) -> dict:
    from app.agents.research_agent import ResearchAgent
    from app.models.schemas import SourceType

    agent = ResearchAgent()
    obs = await agent._extract_observations(
        inputs["competitor"], SourceType(inputs["source_type"]), inputs["source_url"], inputs["raw_text"]
    )
    return {"observations": [o.model_dump() for o in obs]}


def run_research_eval():
    client = _require_langsmith()
    if not client:
        return
    from langsmith.evaluation import evaluate

    dataset = _get_or_create_dataset(client, "research_agent_eval", RESEARCH_EXAMPLES)
    evaluate(
        _research_target,
        data=dataset.name,
        evaluators=[eval_research_source_url_fidelity, eval_research_skips_garbage],
        experiment_prefix="research_agent",
    )


# ---------------------------------------------------------------------------
# Fact-Checker Agent
# ---------------------------------------------------------------------------

FACT_CHECKER_EXAMPLES = [
    {
        "inputs": {
            "competitor": "Acme Corp",
            "observations": [
                {"id": "o1", "source_url": "https://a.example.com/1", "text": "Acme raised Pro plan price to $59/mo."},
                {"id": "o2", "source_url": "https://b.example.com/2", "text": "Acme's Pro tier now costs $59 per month, up from $49."},
            ],
        },
    },
    {
        "inputs": {
            "competitor": "Beta Analytics",
            "observations": [
                {"id": "o3", "source_url": "https://c.example.com/3", "text": "Beta Analytics hired a new VP of Sales."},
            ],
        },
    },
]


def eval_fact_checker_ids_are_real(run, example) -> dict:
    """supporting_source_urls returned for every claim must be a subset of
    the source_urls actually present in the input observations - catches
    the LLM citing a source that was never given to it."""
    valid_urls = {o["source_url"] for o in example.inputs["observations"]}
    claims = run.outputs.get("claims", []) if run.outputs else []
    ok = all(set(c.get("supporting_source_urls", [])).issubset(valid_urls) for c in claims)
    return {"key": "ids_are_real", "score": 1.0 if ok else 0.0}


def eval_fact_checker_confirmation_threshold(run, example) -> dict:
    """A claim marked CONFIRMED must actually have >= MIN_SOURCES_TO_CONFIRM
    unique source_urls - this is the exact rule described to the user
    earlier in this project; the eval enforces the code keeps matching it."""
    claims = run.outputs.get("claims", []) if run.outputs else []
    ok = all(
        len(set(c.get("supporting_source_urls", []))) >= settings.MIN_SOURCES_TO_CONFIRM
        for c in claims
        if c.get("status") == "confirmed"
    )
    return {"key": "confirmation_threshold", "score": 1.0 if ok else 0.0}


async def _fact_checker_target(inputs: dict) -> dict:
    from app.agents.fact_checker_agent import FactCheckerAgent
    from app.models.schemas import RawObservation, SourceType

    observations = [
        RawObservation(id=o["id"], competitor=inputs["competitor"], source_type=SourceType.NEWS_ARTICLE,
                        source_url=o["source_url"], title="", text=o["text"])
        for o in inputs["observations"]
    ]
    claims = await FactCheckerAgent().verify(observations)
    return {"claims": [c.model_dump() for c in claims]}


def run_fact_checker_eval():
    client = _require_langsmith()
    if not client:
        return
    from langsmith.evaluation import evaluate

    dataset = _get_or_create_dataset(client, "fact_checker_agent_eval", FACT_CHECKER_EXAMPLES)
    evaluate(
        _fact_checker_target,
        data=dataset.name,
        evaluators=[eval_fact_checker_ids_are_real, eval_fact_checker_confirmation_threshold],
        experiment_prefix="fact_checker_agent",
    )


# ---------------------------------------------------------------------------
# Graph-Builder Agent
# ---------------------------------------------------------------------------

GRAPH_BUILDER_EXAMPLES = [
    {
        "inputs": {
            "competitor": "Acme Corp",
            "claim_type": "price_change",
            "claim": "Acme Corp raised its Pro plan price from $49/month to $59/month.",
            "status": "confirmed",
        },
    },
]


def eval_graph_builder_allowed_labels(run, example) -> dict:
    """Every entity label / relationship type in the output must be in the
    whitelist enforced in graph_builder_agent.py (ALLOWED_LABELS /
    ALLOWED_REL_TYPES) - this is the same check the code applies before a
    Neo4j write, re-verified here so a prompt change can't silently
    reopen the Cypher-injection surface without the eval catching it."""
    from app.agents.graph_builder_agent import ALLOWED_LABELS, ALLOWED_REL_TYPES

    entities = run.outputs.get("entities", []) if run.outputs else []
    relationships = run.outputs.get("relationships", []) if run.outputs else []
    ok = all(e["label"] in ALLOWED_LABELS for e in entities) and all(
        r["rel_type"] in ALLOWED_REL_TYPES for r in relationships
    )
    return {"key": "allowed_labels", "score": 1.0 if ok else 0.0}


def eval_graph_builder_has_competitor_node(run, example) -> dict:
    """The competitor named in the claim must always end up as a Competitor
    entity - graph_builder_agent.py has explicit fallback logic for this;
    the eval checks that fallback actually fires when needed."""
    entities = run.outputs.get("entities", []) if run.outputs else []
    ok = any(e["label"] == "Competitor" and e["key"] == example.inputs["competitor"] for e in entities)
    return {"key": "has_competitor_node", "score": 1.0 if ok else 0.0}


async def _graph_builder_target(inputs: dict) -> dict:
    from app.agents.graph_builder_agent import GraphBuilderAgent
    from app.models.schemas import VerifiedClaim, VerificationStatus

    claim = VerifiedClaim(
        id="eval-claim", competitor=inputs["competitor"], claim=inputs["claim"], claim_type=inputs["claim_type"],
        status=VerificationStatus(inputs["status"]), supporting_source_urls=["https://example.com/eval"], confidence=0.9,
    )
    entities, relationships = await GraphBuilderAgent()._extract_graph_pieces(claim)
    return {
        "entities": [e.model_dump() for e in entities],
        "relationships": [r.model_dump() for r in relationships],
    }


def run_graph_builder_eval():
    client = _require_langsmith()
    if not client:
        return
    from langsmith.evaluation import evaluate

    dataset = _get_or_create_dataset(client, "graph_builder_agent_eval", GRAPH_BUILDER_EXAMPLES)
    evaluate(
        _graph_builder_target,
        data=dataset.name,
        evaluators=[eval_graph_builder_allowed_labels, eval_graph_builder_has_competitor_node],
        experiment_prefix="graph_builder_agent",
    )


# ---------------------------------------------------------------------------
# Q&A Agent - the key eval for "is this actually dynamic"
# ---------------------------------------------------------------------------

QA_EXAMPLES = [
    {"inputs": {"question": "Which competitors have changed their pricing more than once recently?"}},
    {"inputs": {"question": "Is anyone talking about AI features in their announcements?"}},
    {"inputs": {"question": "What is the capital of France?"}},  # out-of-domain: should NOT call a tool
]


def eval_qa_uses_a_tool_when_relevant(run, example) -> dict:
    """The whole point of qa_agent.py vs. the old hardcoded analyst logic:
    for an in-domain competitive-intel question, the model must actually
    call semantic_search or graph_query rather than answering from
    ungrounded general knowledge. Skipped (N/A -> 1.0) for the deliberately
    out-of-domain example, where NOT calling a tool is the correct
    behavior."""
    if "capital of France" in example.inputs["question"]:
        return {"key": "uses_tool_when_relevant", "score": 1.0}
    tools_used = run.outputs.get("tools_used", []) if run.outputs else []
    return {"key": "uses_tool_when_relevant", "score": 1.0 if tools_used else 0.0}


def eval_qa_answer_not_empty(run, example) -> dict:
    answer = (run.outputs or {}).get("answer", "")
    return {"key": "answer_not_empty", "score": 1.0 if answer.strip() else 0.0}


def eval_qa_sources_present_when_grounded(run, example) -> dict:
    """When a tool was used and the answer isn't the "not enough data"
    fallback (check_answer_grounded in guardrails.py), the response should
    include the retrieved sources so the user can verify the answer
    themselves - this is the eval-side check for that guardrail."""
    outputs = run.outputs or {}
    tools_used = outputs.get("tools_used", [])
    answer = outputs.get("answer", "")
    if not tools_used or "don't have enough verified data" in answer:
        return {"key": "sources_present_when_grounded", "score": 1.0}
    return {"key": "sources_present_when_grounded", "score": 1.0 if outputs.get("sources") else 0.0}


async def _qa_target(inputs: dict) -> dict:
    from app.agents.qa_agent import QAAgent

    result = await QAAgent().answer(inputs["question"])
    return result.model_dump()


def run_qa_eval():
    client = _require_langsmith()
    if not client:
        return
    from langsmith.evaluation import evaluate

    dataset = _get_or_create_dataset(client, "qa_agent_eval", QA_EXAMPLES)
    evaluate(
        _qa_target,
        data=dataset.name,
        evaluators=[eval_qa_uses_a_tool_when_relevant, eval_qa_answer_not_empty, eval_qa_sources_present_when_grounded],
        experiment_prefix="qa_agent",
    )


# ---------------------------------------------------------------------------
# Change-Log summarization (topic-filtered narrative on top of the
# deterministic diff - see changelog_agent.py docstring)
# ---------------------------------------------------------------------------

CHANGELOG_EXAMPLES = [
    {
        "inputs": {
            "topics": ["pricing"],
            "entries": [
                {"competitor": "Acme", "change_type": "modified", "description": "Acme::Pro Plan --PRICED_AT--> $59/mo"},
                {"competitor": "Acme", "change_type": "new", "description": "Acme --POSTED_ROLE--> Backend Engineer"},
            ],
        },
    },
    {
        "inputs": {
            "topics": [],  # no topics configured -> must short-circuit to empty, no LLM call needed
            "entries": [
                {"competitor": "Beta", "change_type": "new", "description": "Beta --LAUNCHED--> New Dashboard"},
            ],
        },
    },
]


def eval_changelog_empty_when_no_topics(run, example) -> dict:
    if example.inputs["topics"]:
        return {"key": "empty_when_no_topics", "score": 1.0}
    summary = (run.outputs or {}).get("summary", "")
    return {"key": "empty_when_no_topics", "score": 1.0 if summary == "" else 0.0}


def eval_changelog_indices_in_range(run, example) -> dict:
    """relevant_indices must reference real entries in the input list -
    this is the same enforcement changelog_agent.py applies in code
    (never trust the LLM's indices blindly), re-verified here."""
    n = len(example.inputs["entries"])
    indices = (run.outputs or {}).get("relevant_indices", [])
    ok = all(isinstance(i, int) and 0 <= i < n for i in indices)
    return {"key": "indices_in_range", "score": 1.0 if ok else 0.0}


async def _changelog_target(inputs: dict) -> dict:
    from app.agents.changelog_agent import ChangeLogAgent
    from app.models.schemas import ChangeLogEntry

    entries = [ChangeLogEntry(**e) for e in inputs["entries"]]
    summary, indices = await ChangeLogAgent().summarize_relevant_changes(entries, inputs["topics"])
    return {"summary": summary, "relevant_indices": indices}


def run_changelog_eval():
    client = _require_langsmith()
    if not client:
        return
    from langsmith.evaluation import evaluate

    dataset = _get_or_create_dataset(client, "changelog_summary_eval", CHANGELOG_EXAMPLES)
    evaluate(
        _changelog_target,
        data=dataset.name,
        evaluators=[eval_changelog_empty_when_no_topics, eval_changelog_indices_in_range],
        experiment_prefix="changelog_summary",
    )


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

ALERTING_EXAMPLES = [
    {"inputs": {"competitor": "Acme Corp", "headline": "Acme Corp raises $50M Series C led by Sequoia"}},
    {"inputs": {"competitor": "Beta Analytics", "headline": "Beta Analytics publishes new blog post: '5 tips for dashboards'"}},
]


def eval_alerting_severity_valid(run, example) -> dict:
    alerts = run.outputs.get("alerts", []) if run.outputs else []
    ok = all(a.get("severity") in ("low", "medium", "high") for a in alerts)
    return {"key": "severity_valid", "score": 1.0 if ok else 0.0}


def eval_alerting_ignores_routine_content(run, example) -> dict:
    """The blog-post example is routine content marketing per
    ALERT_SYSTEM_PROMPT's own instructions - it should not be flagged
    medium/high."""
    if "blog post" not in example.inputs["headline"]:
        return {"key": "ignores_routine_content", "score": 1.0}
    alerts = run.outputs.get("alerts", []) if run.outputs else []
    flagged = any(a.get("severity") in ("medium", "high") for a in alerts)
    return {"key": "ignores_routine_content", "score": 0.0 if flagged else 1.0}


async def _alerting_target(inputs: dict) -> dict:
    from app.services.alerting import ALERT_SYSTEM_PROMPT
    from app.agents.llm import call_llm, extract_json
    from app.services.guardrails import check_output_json_schema

    # Uses a single synthetic headline rather than services.alerting.check_for_alerts
    # directly, since that function calls the live NewsAPI tool - this keeps
    # the eval deterministic/offline instead of depending on external search
    # results changing day to day.
    payload = f"- {inputs['headline']} | https://example.com/eval | {inputs['headline']}"
    response = await call_llm(ALERT_SYSTEM_PROMPT, f"Competitor: {inputs['competitor']}\n\n{payload}", step="eval.alerting")
    try:
        items = extract_json(response)
    except Exception:
        items = []
    items = [i for i in items if check_output_json_schema(i, {"headline", "severity"}, step="eval.alerting")]
    return {"alerts": items}


def run_alerting_eval():
    client = _require_langsmith()
    if not client:
        return
    from langsmith.evaluation import evaluate

    dataset = _get_or_create_dataset(client, "alerting_eval", ALERTING_EXAMPLES)
    evaluate(
        _alerting_target,
        data=dataset.name,
        evaluators=[eval_alerting_severity_valid, eval_alerting_ignores_routine_content],
        experiment_prefix="alerting",
    )


# ---------------------------------------------------------------------------
# Shared helpers + entrypoint
# ---------------------------------------------------------------------------

def _get_or_create_dataset(client, name: str, examples: list[dict]):
    try:
        return client.read_dataset(dataset_name=name)
    except Exception:
        dataset = client.create_dataset(dataset_name=name)
        for ex in examples:
            client.create_example(inputs=ex["inputs"], outputs=ex.get("outputs", {}), dataset_id=dataset.id)
        return dataset


AGENTS = {
    "research": run_research_eval,
    "fact_checker": run_fact_checker_eval,
    "graph_builder": run_graph_builder_eval,
    "qa": run_qa_eval,
    "alerting": run_alerting_eval,
    "changelog": run_changelog_eval,
}


def main():
    requested = sys.argv[1:] or list(AGENTS.keys())
    for name in requested:
        if name not in AGENTS:
            print(f"Unknown agent '{name}'. Choices: {', '.join(AGENTS)}")
            continue
        print(f"--- Running eval: {name} ({date.today().isoformat()}) ---")
        AGENTS[name]()


if __name__ == "__main__":
    main()
