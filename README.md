# Competitive Intelligence & Market Watch Agent

A standing multi-agent system that tracks named competitors' pricing pages,
press releases, and job postings, and produces a weekly, source-verified
executive brief with a "what changed" section.

https://github.com/user-attachments/assets/aa3feb08-a704-458f-bff5-7073abcef645

## Architecture

```
                     ┌─────────────────────┐
   MCP tools ──────► │   Research Agent     │
 (web/news search,   └──────────┬───────────┘
  pricing fetch,                │ RawObservation[]
  career scrape,     ┌──────────▼───────────┐
  telegram post)      │ Fact-Checker Agent    │  >=2 independent sources → CONFIRMED
                     └──────────┬───────────┘
                                │ VerifiedClaim[]
                     ┌──────────▼───────────┐
                     │ Graph-Builder Agent   │──► Neo4j (knowledge graph)
                     └──────────┬───────────┘
                                │
                     ┌──────────▼───────────┐
                     │ Analyst Agent (GraphRAG)│──► Neo4j (traversal) + Qdrant (semantic)
                     └──────────┬───────────┘
                                │ CompetitiveBrief (no change_log yet)
                     ┌──────────▼───────────┐
                     │ Change-Log Agent      │──► diff vs last week's Neo4j snapshot
                     └──────────┬───────────┘
                                │
                          CompetitiveBrief ──► PostgreSQL (history) + Telegram
```

Orchestration: LangGraph `StateGraph`, sequential handoff (`research → fact_check →
graph_builder → analyst → changelog`). See `backend/app/graph/orchestrator.py`.

Two more agents run outside that weekly graph, on demand:

- **Social Listening Agent** (`app/agents/social_listening_agent.py`) — given
  up to 5 competitor names, searches Twitter/X, LinkedIn, and Reddit (via
  SerpAPI site-search, `app/mcp/mcp_server.py::social_listening_search`) and
  scores each competitor 1-10 on tone & voice, pricing clarity, hiring
  signal, social momentum, and content velocity. `POST /api/v1/social/scan`.
- **Competitor Discovery Agent** (`app/agents/competitor_discovery_agent.py`)
  — given YOUR company name, searches the web for its real competitors
  (`app/mcp/mcp_server.py::discover_competitors_search`) and returns
  suggestions to review before adding any to the tracked list.
  `POST /api/v1/competitors/discover`.

Memory: long-term, persisted in Neo4j (graph state, survives across weekly runs)
and PostgreSQL (brief + snapshot history) — not LangGraph's own short-term
per-run checkpointer.

Retrieval: GraphRAG — Cypher traversal answers relationship questions ("who
raised prices twice this quarter"), Qdrant vector search answers semantic
questions ("who is talking about AI features"); the Analyst Agent combines both.

## Repo layout

```
backend/                FastAPI + LangGraph agents + Neo4j/Qdrant/Postgres + FastMCP tool server
frontend-streamlit/      Streamlit dashboard (fastest to run locally)
frontend-next/           Next.js dashboard (production-style UI, same API)
docker-compose.yml        Runs the whole stack: neo4j, qdrant, postgres, mcp-server, backend, both frontends
```

Both frontends talk to the same FastAPI backend — pick whichever fits your
deployment target, or run both.

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env   # fill in GROQ_API_KEY, NEWS_API_KEY, TELEGRAM_BOT_TOKEN (Telegram optional)
docker compose up --build
```

- Backend API: http://localhost:8000/docs
- Streamlit: http://localhost:8501
- Next.js: http://localhost:3000
- Neo4j browser: http://localhost:7474

## Quick start (local, no Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # point NEO4J_URI/QDRANT_URL/POSTGRES_DSN at local instances
python -m app.mcp.mcp_server &     # MCP tool server on :8765
uvicorn app.main:app --reload      # API on :8000

# Streamlit frontend
cd frontend-streamlit
pip install -r requirements.txt
streamlit run app.py

# Next.js frontend
cd frontend-next
npm install
cp .env.local.example .env.local
npm run dev
```

You still need Neo4j, Qdrant, and PostgreSQL running locally (or point the
`.env` at hosted instances) even outside Docker.

## API keys — what's free and what's optional

| Key | Required? | Free tier? | Where to get it |
|---|---|---|---|
| `LLM_PROVIDER` + (`GROQ_API_KEY` or `OPENAI_API_KEY`) | Yes — powers every agent's LLM calls | Groq: yes, free. OpenAI: paid. | Set `LLM_PROVIDER=groq` and get a key at https://console.groq.com/keys, **or** set `LLM_PROVIDER=openai` and get a key at https://platform.openai.com/api-keys. Only fill in the key for the one you pick. |
| `NEWS_API_KEY` | Optional — without it, news search just returns no results | Yes (dev tier: 100 req/day, 24h-delayed results, non-commercial) | https://newsapi.org/register |
| `SERPAPI_KEY` | Optional — without it, Social Listening and Competitor Discovery just return no results | Yes (100 searches/month free) | https://serpapi.com/manage-api-key |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional — without it, Telegram posting is skipped silently | Free | Message [@BotFather](https://t.me/BotFather) → `/newbot` → get the token. Get `TELEGRAM_CHAT_ID` by adding the bot to your group/channel and calling `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending it a message — the `chat.id` field in the response is what you need. |
| Embeddings (`app/services/embeddings.py` uses `voyageai` by default) | Optional to swap for another provider | Voyage has a free tier too | https://www.voyageai.com |

Nothing else in the stack needs a paid key — Neo4j, Qdrant, and Postgres all
run locally via Docker Compose for free.

## Triggering a run

- UI: click "Run weekly pipeline now" on either frontend's dashboard.
- API: `POST /api/v1/briefs/run`
- Scheduled: `backend/app/services/scheduler.py` runs it automatically per
  `WEEKLY_RUN_CRON` (default Monday 08:00) via APScheduler, plus a separate
  alert poll every `ALERT_POLL_MINUTES` for the bonus real-time alerting agent.

## Social Listening & Competitor Discovery

Two on-demand features, separate from the weekly pipeline:

- **Discover competitors**: Competitors page → "Discover competitors" → enter
  your own company → review the suggested list → click "Add" on the ones you
  want tracked. Same as calling `POST /api/v1/competitors/discover {"company": "..."}`.
- **Social Listening**: Streamlit `pages/5_Social_Listening.py` or Next.js
  `/social` → enter up to 5 competitor names → get a scorecard per competitor
  (tone/voice, pricing clarity, hiring signal, social momentum, content
  velocity, 1-10 each with a rationale). Same as calling
  `POST /api/v1/social/scan {"competitors": ["...", ...]}`.

Both require `SERPAPI_KEY` in `backend/.env` — without it they return empty
results rather than erroring.

## Bonus features implemented

- **Sentiment scoring** — `app/services/sentiment.py`, tags Announcement nodes.
- **Real-time alerting** — `app/services/alerting.py`, pings Telegram immediately
  on high-severity events instead of waiting for the weekly cycle.
- **Interactive graph visualization** — Plotly network graph in Streamlit
  (`pages/3_Knowledge_Graph.py`) and a force-directed graph in Next.js
  (`components/GraphExplorer.tsx`), both reading `/api/v1/graph/snapshot`.

## Notes / what to harden before production

- `POST /api/v1/graph/query` runs arbitrary Cypher — sandbox or remove before
  exposing publicly.
- `scrape_career_page` is a stub; wire it to each competitor's actual ATS API
  (Greenhouse/Lever/Ashby) rather than raw HTML scraping.
- Swap `voyageai` in `app/services/embeddings.py` for whatever embedding
  provider you standardize on; just keep the `embed_text`/`embed_documents`
  function signatures.
