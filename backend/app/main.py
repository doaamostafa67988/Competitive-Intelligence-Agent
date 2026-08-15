"""
FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.postgres_client import init_models
from app.db.neo4j_client import get_neo4j_client
from app.services.scheduler import start_scheduler
from app.api import routes_brief, routes_competitors, routes_graph, routes_social

settings = get_settings()
logger = logging.getLogger("startup")


async def _retry(coro_fn, name: str, attempts: int = 15, delay_seconds: float = 2.0):
    """Retry a startup dependency (DB connection etc.) with a fixed backoff.

    Docker Compose's `depends_on` only waits for a container to *start*, not
    for the service inside it to actually be ready to accept connections —
    Neo4j and Postgres both take a few extra seconds after their container
    starts before they'll accept Bolt/SQL connections. This gives them room
    to finish booting instead of crashing the backend on the first attempt.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = coro_fn()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:  # noqa: BLE001 - intentionally broad: any connection error should retry
            last_error = e
            logger.warning("%s not ready yet (attempt %d/%d): %s", name, attempt, attempts, e)
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"{name} did not become ready after {attempts} attempts") from last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _retry(init_models, "Postgres")
    await _retry(lambda: get_neo4j_client().ensure_constraints(), "Neo4j")
    start_scheduler()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production to the Next.js / Streamlit origins
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_brief.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_competitors.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_graph.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_social.router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
