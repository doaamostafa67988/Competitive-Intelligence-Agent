"""
LangGraph orchestration: Sequential handoff across
  Research -> Social-Listening -> Fact-Checker -> Graph-Builder -> Analyst -> Change-Log
This is the weekly (and on-demand) pipeline that produces one CompetitiveBrief.

Orchestration pattern: sequential handoff (each agent's output is the next
agent's input; no branching/parallel fan-out needed for this workflow, though
Research calls per competitor could be parallelized with LangGraph's Send API
if desired).
Memory type: long-term, persisted in Neo4j (graph state) + Postgres
(brief/snapshot history) - survives across weekly runs, unlike LangGraph's
own short-term checkpointer which only covers a single run's state.
"""
from __future__ import annotations
import json
from typing import List, Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END

from app.agents.research_agent import ResearchAgent
from app.agents.fact_checker_agent import FactCheckerAgent
from app.agents.graph_builder_agent import GraphBuilderAgent
from app.agents.analyst_agent import AnalystAgent
from app.agents.changelog_agent import ChangeLogAgent
from app.agents.social_listening_agent import SocialListeningAgent
from app.models.schemas import RawObservation, VerifiedClaim, CompetitiveBrief, BriefSection, SocialScorecard
from app.services.embeddings import embed_text


class CompetitorTarget(TypedDict):
    name: str
    pricing_url: Optional[str]
    careers_url: Optional[str]


class PipelineState(TypedDict, total=False):
    targets: List[CompetitorTarget]
    observations: List[RawObservation]
    claims: List[VerifiedClaim]
    previous_snapshot: Optional[list]
    graph_updated: bool
    social_scorecards: List[SocialScorecard]
    brief: CompetitiveBrief


research_agent = ResearchAgent()
fact_checker_agent = FactCheckerAgent()
graph_builder_agent = GraphBuilderAgent()
analyst_agent = AnalystAgent()
changelog_agent = ChangeLogAgent()
social_listening_agent = SocialListeningAgent()


async def research_node(state: PipelineState) -> PipelineState:
    all_obs: List[RawObservation] = []
    for target in state["targets"]:
        obs = await research_agent.gather_for_competitor(
            target["name"], target.get("pricing_url"), target.get("careers_url")
        )
        all_obs.extend(obs)
    return {"observations": all_obs}


async def social_listening_node(state: PipelineState) -> PipelineState:
    # Capped to the first 5 targets (same cap as the standalone /social/scan
    # endpoint) to keep SerpAPI + LLM usage bounded on every pipeline run.
    names = [t["name"] for t in state["targets"]]
    scorecards = await social_listening_agent.scan_many(names)
    return {"social_scorecards": scorecards}


async def fact_check_node(state: PipelineState) -> PipelineState:
    claims = await fact_checker_agent.verify(state["observations"])
    return {"claims": claims}


async def graph_builder_node(state: PipelineState) -> PipelineState:
    await graph_builder_agent.build_and_write(state["claims"])
    return {"graph_updated": True}


async def analyst_node(state: PipelineState) -> PipelineState:
    competitors = [t["name"] for t in state["targets"]]
    brief = await analyst_agent.synthesize_brief(competitors, state["claims"], embed_text)
    return {"brief": brief}


def _build_social_section(scorecards: List[SocialScorecard]) -> BriefSection:
    dims = [
        ("Tone & Voice", "tone_voice"),
        ("Pricing Clarity", "pricing_clarity"),
        ("Hiring Signal", "hiring_signal"),
        ("Social Momentum", "social_momentum"),
        ("Content Velocity", "content_velocity"),
    ]
    lines: List[str] = []
    cited: List[str] = []
    for card in scorecards:
        lines.append(f"**{card.competitor}**")
        lines.append(card.overall_summary)
        for label, key in dims:
            dim = getattr(card, key)
            lines.append(f"- {label}: {dim.score}/10 — {dim.label}. {dim.rationale}")
        lines.append("")
        cited.extend(p.url for p in card.sample_posts[:3] if p.url)
    return BriefSection(
        heading="Social Listening (Twitter/X, LinkedIn, Reddit)",
        body_markdown="\n".join(lines).strip(),
        cited_source_urls=cited,
    )


async def compile_social_node(state: PipelineState) -> PipelineState:
    scorecards = state.get("social_scorecards") or []
    brief = state["brief"]
    if scorecards:
        brief.sections.append(_build_social_section(scorecards))
    return {"brief": brief}


async def changelog_node(state: PipelineState) -> PipelineState:
    entries = changelog_agent.diff_against_snapshot(state.get("previous_snapshot"))
    brief = state["brief"]
    brief.change_log = entries
    return {"brief": brief}


def build_pipeline():
    graph = StateGraph(PipelineState)
    graph.add_node("research", research_node)
    graph.add_node("social_listening", social_listening_node)
    graph.add_node("fact_check", fact_check_node)
    graph.add_node("graph_builder", graph_builder_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("compile_social", compile_social_node)
    graph.add_node("changelog", changelog_node)

    graph.set_entry_point("research")
    graph.add_edge("research", "social_listening")
    graph.add_edge("social_listening", "fact_check")
    graph.add_edge("fact_check", "graph_builder")
    graph.add_edge("graph_builder", "analyst")
    graph.add_edge("analyst", "compile_social")
    graph.add_edge("compile_social", "changelog")
    graph.add_edge("changelog", END)

    return graph.compile()


pipeline = build_pipeline()


async def run_weekly_pipeline(targets: List[CompetitorTarget], previous_snapshot: list | None) -> CompetitiveBrief:
    result: PipelineState = await pipeline.ainvoke(
        {"targets": targets, "previous_snapshot": previous_snapshot}
    )
    return result["brief"]

