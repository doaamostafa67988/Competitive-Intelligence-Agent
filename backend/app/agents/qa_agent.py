"""
Q&A Agent
---------
Role: answers an arbitrary free-text question from a user about tracked
competitors ("who raised prices twice this quarter", "who's talking about
AI features", "what has Acme announced recently") without a hardcoded query
shape.

This is deliberately different from the Analyst Agent: analyst_agent.py
always runs the exact same fixed Cypher query and the same 3 hardcoded
vector-search themes on every pipeline run, because a weekly brief needs
consistent, predictable sections. This agent instead lets the LLM pick
*which* lookup(s) answer the specific question asked, via OpenAI-style
function-calling (see agents/llm.py::call_llm_with_tools) - that's what
makes the Q&A dynamic instead of a fixed set of questions.

Safety note (see agents/graph_builder_agent.py's ALLOWED_LABELS comment for
the same concern): the LLM is never given raw Cypher access. graph_query
below only accepts one of a few pre-approved `question_type` values, each
mapped to a fixed, parameterized Cypher template in neo4j_client.py - the
LLM chooses *which* pre-approved question to ask and with what filter
values, never what the query itself looks like. That keeps this agent
exploitable the same way tool-calling always is (a bad `competitor` string
argument), but not exploitable via Cypher injection.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Any
from app.agents.llm import call_llm_with_tools
from app.db.neo4j_client import get_neo4j_client
from app.db.qdrant_client import get_vector_store
from app.services.embeddings import embed_text
from app.services.guardrails import check_answer_grounded, check_contextual_compliance, check_input_text, redact_pii
from app.services.logging_utils import truncate_for_log
from app.models.schemas import QAAnswer

rag_logger = logging.getLogger("rag")  # before/after retrieval - same logger as research_agent.py / analyst_agent.py

QA_SYSTEM_PROMPT = """You are a competitive-intelligence analyst answering a
specific question from a SaaS company's team about tracked competitors.
Use the semantic_search and graph_query tools as needed to gather real data
before answering - do not answer from general knowledge, and do not invent
facts not returned by a tool. If the tools return nothing relevant, say so
plainly rather than guessing. Cite which competitor each fact is about.
Keep the answer to a few sentences unless the question asks for a list."""

QA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": (
                "Search competitor announcements, press releases, pricing pages, and "
                "job postings by meaning/topic - use for open-ended thematic questions "
                "like 'who is talking about AI features' or 'any expansion into Europe'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "the topic or question to search for"},
                    "competitor": {"type": "string", "description": "optional: restrict to one competitor"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_query",
            "description": (
                "Answer a structured relationship question about tracked competitors using "
                "the knowledge graph - use for questions about pricing-change frequency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question_type": {
                        "type": "string",
                        "enum": ["repeat_price_changes"],
                        "description": "which pre-approved graph question to run",
                    },
                    "since_days": {"type": "integer", "description": "how many days back to look; default 90"},
                    "min_changes": {"type": "integer", "description": "minimum number of price changes; default 2"},
                },
                "required": ["question_type"],
            },
        },
    },
]


class QAAgent:
    def __init__(self):
        self.neo4j = get_neo4j_client()
        self.vector_store = get_vector_store()
        self._tools_used: list[str] = []
        self._retrieved_items: list[dict] = []

    async def answer(self, question: str) -> QAAnswer:
        self._tools_used = []
        self._retrieved_items = []

        # Input guardrails: same checks applied to scraped text apply here,
        # since a user question is also untrusted free text reaching an LLM
        # prompt directly.
        if not check_contextual_compliance(question, min_length=3):
            return QAAnswer(question=question, answer="Please ask a more specific question.", tools_used=[])
        check_input_text(question, source="qa_user_question")

        response = await call_llm_with_tools(
            QA_SYSTEM_PROMPT,
            question,
            tools=QA_TOOLS,
            tool_executor=self._execute_tool,
            step="qa_agent.answer",
        )
        answer_text = response.strip() or "I couldn't find enough data to answer that question."

        # Output guardrail: don't present a confident-sounding answer if
        # every tool call the model made came back empty/errored - see
        # guardrails.py::check_answer_grounded docstring.
        if not check_answer_grounded(self._tools_used, self._retrieved_items, step="qa_agent.answer"):
            answer_text = (
                "I don't have enough verified data to answer that confidently. "
                "Try rephrasing, or ask about a specific tracked competitor."
            )

        # Output guardrail: redact anything PII-shaped before it reaches the
        # user-facing API response.
        answer_text = redact_pii(answer_text, step="qa_agent.answer")

        # Surface what was actually retrieved so the user can verify the
        # answer themselves, not just take tools_used's word for it.
        sources = [
            {"competitor": i.get("competitor"), "source_url": i.get("source_url")}
            for i in self._retrieved_items
            if isinstance(i, dict) and "error" not in i and i.get("source_url")
        ][:5]

        return QAAnswer(question=question, answer=answer_text, tools_used=self._tools_used, sources=sources)

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> Any:
        self._tools_used.append(name)
        if name == "semantic_search":
            results = await self._semantic_search(args.get("query", ""), args.get("competitor"))
        elif name == "graph_query":
            results = await self._graph_query(
                args.get("question_type", ""), args.get("since_days", 90), args.get("min_changes", 2)
            )
        else:
            results = [{"error": f"unknown tool {name}"}]
        self._retrieved_items.extend(results if isinstance(results, list) else [results])
        return results

    async def _semantic_search(self, query: str, competitor: str | None) -> list[dict]:
        if not query:
            return []
        # --- before retrieval ---
        rag_logger.info("retrieve_start step=qa_agent.semantic_search query=%s competitor=%s", query, competitor)
        try:
            embedding = await embed_text(query)
        except Exception as e:
            rag_logger.info("retrieve_error step=qa_agent.semantic_search query=%s error=%s", query, e)
            return [{"error": f"embedding unavailable: {e}"}]
        hits = self.vector_store.search(embedding, top_k=6, competitor=competitor or None)
        # --- after retrieval ---
        rag_logger.info(
            "retrieve_end step=qa_agent.semantic_search query=%s hit_count=%d hits=%s",
            query, len(hits),
            [{"competitor": h.get("competitor"), "score": h.get("score"), "text": truncate_for_log(h.get("text", ""), 200)} for h in hits],
        )
        return [{"competitor": h.get("competitor"), "source_url": h.get("source_url"), "text": h.get("text", "")[:400]} for h in hits]

    async def _graph_query(self, question_type: str, since_days: int, min_changes: int) -> list[dict]:
        # Whitelist enforced here, not just in the tool schema's `enum` -
        # a tool schema constraint is a hint to the model, not a guarantee;
        # this is the actual enforcement point before any Cypher template
        # runs.
        if question_type != "repeat_price_changes":
            return [{"error": f"unsupported question_type: {question_type}"}]
        since = (date.today() - timedelta(days=max(1, min(since_days, 3650)))).isoformat()
        return self.neo4j.competitors_who_changed_price_n_times(since, n=max(1, min_changes))
