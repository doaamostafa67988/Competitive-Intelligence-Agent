"""
Fact-Checker Agent
-------------------
Role: cross-references raw observations against each other (and, optionally,
an extra corroborating search) before a claim is allowed into the knowledge
graph or the brief. A claim needs >= settings.MIN_SOURCES_TO_CONFIRM
independent source URLs saying the same thing to be CONFIRMED; otherwise it
is kept as UNCONFIRMED (flagged, excluded from headline sections) or
REJECTED if sources actively contradict it.
"""
from __future__ import annotations
import uuid
from collections import defaultdict
from typing import List
from app.agents.llm import call_llm, extract_json
from app.config import get_settings
from app.models.schemas import RawObservation, VerifiedClaim, VerificationStatus
from app.services.guardrails import check_output_json_schema

settings = get_settings()

CLUSTER_SYSTEM_PROMPT = """You are a fact-checking analyst for a competitive
intelligence system. You are given a list of raw observations (each with an
id, source_url, and text) about ONE competitor. Group observations that
describe the SAME underlying fact (e.g. the same price change, the same
product launch) into claims. For each claim, output:
  - claim: a single normalized sentence
  - claim_type: one of price_change, product_launch, announcement, hiring_signal, other
  - supporting_observation_ids: list of observation ids that support it
  - contradicted: true if any observation in the input directly contradicts this claim, else false
Return ONLY a JSON array of these claim objects. Observations that don't
cluster with anything else still form their own single-observation claim."""


class FactCheckerAgent:
    async def verify(self, observations: List[RawObservation]) -> List[VerifiedClaim]:
        if not observations:
            return []

        by_competitor: dict[str, List[RawObservation]] = defaultdict(list)
        for obs in observations:
            by_competitor[obs.competitor].append(obs)

        all_claims: List[VerifiedClaim] = []
        for competitor, obs_list in by_competitor.items():
            all_claims.extend(await self._verify_for_competitor(competitor, obs_list))
        return all_claims

    async def _verify_for_competitor(
        self, competitor: str, observations: List[RawObservation]
    ) -> List[VerifiedClaim]:
        obs_by_id = {o.id: o for o in observations}
        payload = "\n".join(f"- id={o.id} | source={o.source_url} | text={o.text}" for o in observations)
        response = await call_llm(CLUSTER_SYSTEM_PROMPT, f"Competitor: {competitor}\n\nObservations:\n{payload}", step="fact_checker.cluster")

        try:
            clusters = extract_json(response)
        except Exception:
            clusters = []
        if not isinstance(clusters, list):
            clusters = []
        # Output guardrail: each cluster item must at least have "claim" and
        # "supporting_observation_ids" before we build a VerifiedClaim from
        # it - a malformed item here would otherwise silently become a
        # confidence-0 claim with an empty statement.
        clusters = [
            c for c in clusters
            if check_output_json_schema(c, {"claim", "supporting_observation_ids"}, step="fact_checker.cluster")
        ]

        claims: List[VerifiedClaim] = []
        for c in clusters:
            support_ids = [oid for oid in c.get("supporting_observation_ids", []) if oid in obs_by_id]
            source_urls = list({obs_by_id[oid].source_url for oid in support_ids})
            contradicted = bool(c.get("contradicted", False))

            if contradicted:
                status = VerificationStatus.REJECTED
                confidence = 0.1
            elif len(source_urls) >= settings.MIN_SOURCES_TO_CONFIRM:
                status = VerificationStatus.CONFIRMED
                confidence = min(1.0, 0.6 + 0.15 * len(source_urls))
            else:
                status = VerificationStatus.UNCONFIRMED
                confidence = 0.4

            claims.append(
                VerifiedClaim(
                    id=str(uuid.uuid4()),
                    competitor=competitor,
                    claim=c.get("claim", ""),
                    claim_type=c.get("claim_type", "other"),
                    status=status,
                    supporting_source_urls=source_urls,
                    confidence=confidence,
                )
            )
        return claims
