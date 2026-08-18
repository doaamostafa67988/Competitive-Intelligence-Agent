"""
PostgreSQL access for structured, relational records: brief history, run
metadata, raw observation audit trail, and user-defined tracked topics.
SQLAlchemy 2.0 style, async engine.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, JSON, Text, Float, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.config import get_settings

settings = get_settings()

ASYNC_DSN = settings.POSTGRES_DSN.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_DSN, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class BriefRecord(Base):
    __tablename__ = "briefs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    competitors_covered: Mapped[dict] = mapped_column(JSON)
    executive_summary: Mapped[str] = mapped_column(Text)
    sections_json: Mapped[dict] = mapped_column(JSON)
    change_log_json: Mapped[dict] = mapped_column(JSON)
    unconfirmed_claims_json: Mapped[dict] = mapped_column(JSON)
    change_log_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ObservationRecord(Base):
    __tablename__ = "raw_observations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    competitor: Mapped[str] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClaimRecord(Base):
    __tablename__ = "verified_claims"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    competitor: Mapped[str] = mapped_column(String, index=True)
    claim: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    supporting_source_urls_json: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackedTopicRecord(Base):
    """A user-defined subject of interest (e.g. "pricing for enterprise
    tier", "layoffs") - replaces the hardcoded 3-theme list that used to
    live directly in analyst_agent.py. Read by the Analyst Agent's
    thematic vector-search leg and by the Change-Log Agent's
    topic-filtered summary; written/deleted only via api/routes_topics.py."""
    __tablename__ = "tracked_topics"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def save_observations(observations: list) -> None:
    """Persist every RawObservation from a research run as its own row -
    this is the audit trail the ObservationRecord model's docstring already
    promised but nothing was actually calling. Called from
    graph/orchestrator.py's research_node right after Research Agent
    returns, so a competitor's raw scraped/searched data survives even if
    it later gets rejected by the Fact-Checker (rejected claims are still
    worth being able to look up later - the point of an audit trail)."""
    if not observations:
        return
    async with AsyncSessionLocal() as session:
        for obs in observations:
            session.add(ObservationRecord(
                id=obs.id,
                competitor=obs.competitor,
                source_type=obs.source_type.value,
                source_url=obs.source_url,
                title=obs.title,
                text=obs.text,
            ))
        await session.commit()


async def save_claims(claims: list) -> None:
    """Persist every VerifiedClaim (CONFIRMED, UNCONFIRMED, and REJECTED
    alike) from a fact-checking run - same audit-trail gap as
    save_observations above. REJECTED claims are kept too: knowing what got
    rejected and why (contradicted, single-sourced) is exactly the kind of
    thing worth being able to look back on later, and graph_builder_agent.py
    already excludes REJECTED claims from the graph itself, so this is the
    only place that history would otherwise exist at all."""
    if not claims:
        return
    async with AsyncSessionLocal() as session:
        for c in claims:
            session.add(ClaimRecord(
                id=c.id,
                competitor=c.competitor,
                claim=c.claim,
                claim_type=c.claim_type,
                status=c.status.value,
                confidence=c.confidence,
                supporting_source_urls_json=c.supporting_source_urls,
            ))
        await session.commit()


async def list_topics() -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TrackedTopicRecord).order_by(TrackedTopicRecord.created_at))
        return [
            {"id": t.id, "topic": t.topic, "created_at": t.created_at.isoformat()}
            for t in result.scalars().all()
        ]


async def add_topic(topic: str) -> dict:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(TrackedTopicRecord).where(TrackedTopicRecord.topic == topic))
        row = existing.scalar_one_or_none()
        if row:
            return {"id": row.id, "topic": row.topic, "created_at": row.created_at.isoformat()}
        record = TrackedTopicRecord(id=str(uuid.uuid4()), topic=topic)
        session.add(record)
        await session.commit()
        return {"id": record.id, "topic": record.topic, "created_at": record.created_at.isoformat()}


async def delete_topic(topic_id: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TrackedTopicRecord).where(TrackedTopicRecord.id == topic_id))
        row = result.scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.commit()
