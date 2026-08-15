"""
PostgreSQL access for structured, relational records: brief history, run
metadata, and raw observation audit trail. SQLAlchemy 2.0 style, async engine.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, DateTime, JSON, Text, Float
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


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
