"""
Pydantic schemas shared across agents, API routes, and DB layers.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    PRICING_PAGE = "pricing_page"
    PRESS_RELEASE = "press_release"
    JOB_POSTING = "job_posting"
    NEWS_ARTICLE = "news_article"
    SOCIAL_POST = "social_post"


class RawObservation(BaseModel):
    """One unverified fact pulled by the Research Agent, before fact-checking."""
    id: str
    competitor: str
    source_type: SourceType
    source_url: str
    title: str
    text: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class VerificationStatus(str, Enum):
    CONFIRMED = "confirmed"          # corroborated by >= MIN_SOURCES_TO_CONFIRM independent sources
    UNCONFIRMED = "unconfirmed"      # single source, plausible, kept but flagged
    REJECTED = "rejected"            # contradicted by other sources or clearly unreliable


class VerifiedClaim(BaseModel):
    """Output of the Fact-Checker Agent."""
    id: str
    competitor: str
    claim: str  # normalized natural-language claim, e.g. "Acme raised Pro plan price to $49/mo"
    claim_type: Literal["price_change", "product_launch", "announcement", "hiring_signal", "other"]
    status: VerificationStatus
    supporting_source_urls: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=datetime.utcnow)


class GraphEntity(BaseModel):
    """Node to upsert into Neo4j."""
    label: Literal["Competitor", "Product", "PricePoint", "Announcement", "JobPosting"]
    key: str  # unique natural key, e.g. "Acme::Pro Plan"
    properties: dict = Field(default_factory=dict)


class GraphRelationship(BaseModel):
    """Edge to upsert into Neo4j, connecting two GraphEntity keys."""
    from_key: str
    to_key: str
    rel_type: str  # e.g. RAISED_PRICE_ON, LAUNCHED, ANNOUNCED, POSTED_ROLE
    properties: dict = Field(default_factory=dict)


class GraphUpdate(BaseModel):
    """Output of the Graph-Builder Agent for one run."""
    entities: List[GraphEntity]
    relationships: List[GraphRelationship]
    source_claim_ids: List[str]


class ChangeLogEntry(BaseModel):
    competitor: str
    change_type: Literal["new", "modified", "removed"]
    description: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None


class BriefSection(BaseModel):
    heading: str
    body_markdown: str
    cited_source_urls: List[str] = Field(default_factory=list)


class CompetitiveBrief(BaseModel):
    id: str
    run_date: datetime = Field(default_factory=datetime.utcnow)
    competitors_covered: List[str]
    executive_summary: str
    sections: List[BriefSection]
    change_log: List[ChangeLogEntry]
    unconfirmed_claims: List[str] = Field(default_factory=list)


class SocialPlatform(str, Enum):
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"


class SocialPost(BaseModel):
    """One raw post/mention surfaced by the Social Listening Agent's search."""
    platform: SocialPlatform
    title: str
    url: str
    snippet: str
    published_at: Optional[str] = None


class DimensionScore(BaseModel):
    """One scored dimension (tone/voice, pricing clarity, hiring signal,
    social momentum, content velocity) in a SocialScorecard."""
    score: int = Field(ge=1, le=10)
    label: str
    rationale: str


class SocialScorecard(BaseModel):
    """Output of the Social Listening Agent for one competitor: an ad-hoc
    scan of Twitter/X, LinkedIn, and Reddit scored across five dimensions."""
    id: str
    competitor: str
    scanned_at: datetime = Field(default_factory=datetime.utcnow)
    platforms_covered: List[SocialPlatform]
    tone_voice: DimensionScore
    pricing_clarity: DimensionScore
    hiring_signal: DimensionScore
    social_momentum: DimensionScore
    content_velocity: DimensionScore
    overall_summary: str
    sample_posts: List[SocialPost] = Field(default_factory=list)


class CompetitorSuggestion(BaseModel):
    """Output of the Competitor Discovery Agent: one candidate competitor
    surfaced for a given company, not yet added to the tracked list."""
    name: str
    reason: str


class AlertEvent(BaseModel):
    id: str
    competitor: str
    severity: Literal["low", "medium", "high"]
    headline: str
    detail: str
    source_url: str
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
