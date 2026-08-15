"""
Central configuration for the Competitive Intelligence & Market Watch Agent backend.
All values are read from environment variables so the same image can run in
dev / staging / prod without code changes.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Competitive Intelligence & Market Watch Agent"
    ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- LLM ---
    # LLM_PROVIDER selects which client agents/llm.py builds: "groq" (free
    # tier, https://console.groq.com/keys) or "openai" (paid,
    # https://platform.openai.com/api-keys). Only the key for the provider
    # you pick needs to be filled in.
    LLM_PROVIDER: str = "groq"  # "groq" | "openai"
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "llama-3.3-70b-versatile"  # e.g. "gpt-4o-mini" if LLM_PROVIDER=openai
    LLM_TEMPERATURE: float = 0.2

    # --- Neo4j (knowledge graph) ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "changeme"

    # --- Qdrant (vector store for announcement text) ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "announcements"
    QDRANT_API_KEY: str = ""

    # --- PostgreSQL (brief history / run metadata) ---
    POSTGRES_DSN: str = "postgresql://postgres:postgres@localhost:5432/competitive_intel"

    # --- Tooling / MCP ---
    MCP_SERVER_URL: str = "http://localhost:8765/mcp"
    WEB_SEARCH_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # --- SerpAPI (social listening: site-restricted search across
    # Twitter/X, LinkedIn, Reddit) -> https://serpapi.com/manage-api-key ---
    SERPAPI_KEY: str = ""

    # --- Tracked competitors (seed config; can be moved to DB/UI later) ---
    TRACKED_COMPETITORS: List[str] = []

    # --- Scheduling ---
    WEEKLY_RUN_CRON: str = "0 8 * * MON"  # 08:00 every Monday
    ALERT_POLL_MINUTES: int = 30

    # --- Fact-checking ---
    MIN_SOURCES_TO_CONFIRM: int = 2

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
