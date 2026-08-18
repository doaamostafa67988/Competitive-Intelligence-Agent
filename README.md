# Competitive Intelligence & Market Watch Agent

A standing multi-agent system that tracks named competitors' pricing pages,
press releases, and job postings, and produces a weekly, source-verified
executive brief with a "what changed" section.

https://github.com/user-attachments/assets/aa3feb08-a704-458f-bff5-7073abcef645

## Architecture

```
Weekly pipeline (LangGraph StateGraph, sequential handoff):

                     ┌─────────────────────┐
   MCP tools ──────► │   Research Agent     │──► Qdrant (chunked + embedded)
 (web/news search,   └──────────┬───────────┘     also: Postgres audit trail
  pricing fetch,                │ RawObservation[]
  career scrape,     ┌──────────▼───────────┐
  telegram post)      │ Fact-Checker Agent    │  >=2 independent sources → CONFIRMED
                     └──────────┬───────────┘     Postgres audit trail (incl. REJECTED)
                                │ VerifiedClaim[]
                     ┌──────────▼───────────┐
                     │ Graph-Builder Agent   │──► Neo4j (label/rel_type whitelist enforced)
                     └──────────┬───────────┘
                                │
                     ┌──────────▼───────────┐
                     │ Analyst Agent (GraphRAG)│──► Neo4j (traversal) + Qdrant (semantic,
                     └──────────┬───────────┘     topics from user-defined Tracked Topics)
                                │ CompetitiveBrief
                     ┌──────────▼───────────┐
                     │ Change-Log Agent      │──► deterministic diff vs last week's Neo4j
                     └──────────┬───────────┘     snapshot, then an LLM narrative pass
                                │                  filtered to Tracked Topics on top
                          CompetitiveBrief ──► PostgreSQL (history) + Telegram

On-demand (outside the weekly graph):

  User question ──► Q&A Agent ──► LLM picks semantic_search (Qdrant) and/or
  (POST /api/v1/qa)               graph_query (whitelisted Cypher templates)
                                   at runtime, per question - not a fixed
                                   query shape. Answer is grounded-checked
                                   before it's returned; retrieved sources
                                   are included in the response.
```

Orchestration: LangGraph `StateGraph`, sequential handoff (`research → fact_check →
graph_builder → analyst → changelog`). See `backend/app/graph/orchestrator.py`.

Two more agents run outside that weekly graph, on demand:

- **Q&A Agent** (`app/agents/qa_agent.py`) — answers an arbitrary free-text
  question about tracked competitors. Unlike the Analyst Agent (fixed Cypher
  query + fixed theme list every run), this uses real LLM tool-calling
  (`app/agents/llm.py::call_llm_with_tools`) so the model decides at runtime
  whether to run a semantic search, a graph lookup, both, or neither.
  `graph_query` only accepts a whitelisted `question_type` - the LLM never
  gets raw Cypher access. `POST /api/v1/qa {"question": "..."}`. Frontend:
  Next.js `/qa`, Streamlit `pages/6_Ask_a_Question.py`.
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

**Tracked Topics** (`app/api/routes_topics.py`, `POST/GET/DELETE /api/v1/topics`)
replace what used to be a hardcoded 3-theme list: the Analyst Agent's
thematic vector search and the Change-Log Agent's narrative-summary pass
both read from this user-configurable list (falls back to a default set of
3 themes if nothing's configured yet). Managed from Next.js `/qa` or
Streamlit's Ask-a-Question page.

Memory: long-term, persisted in Neo4j (graph state, survives across weekly runs)
and PostgreSQL (brief + snapshot history + raw_observations/verified_claims
audit trail + tracked_topics) — not LangGraph's own short-term per-run
checkpointer.

Retrieval: GraphRAG — Cypher traversal answers relationship questions ("who
raised prices twice this quarter"), Qdrant vector search answers semantic
questions ("who is talking about AI features"); the Analyst Agent combines
both for the weekly brief, and the Q&A Agent picks between them per question.
Qdrant is populated by the Research Agent chunking raw source text
(paragraph/sentence-aware, not fixed-size - `app/services/chunking.py`) and
embedding each chunk (Voyage `voyage-3`) as it's gathered, independent of
whether the Fact-Checker later confirms/rejects the resulting claim.

## Guardrails, evaluation, and tracing

- **Guardrails** (`app/services/guardrails.py`) - input guardrails (prompt-
  injection heuristics on scraped text/user questions, contextual-compliance
  length checks) run before anything reaches an LLM; output guardrails
  (structured-output schema validation, PII redaction before Telegram/API
  responses, Q&A answer groundedness) run on parsed LLM output before it's
  written to a database or shown to a user. Also closes a real Cypher-
  injection surface: `graph_builder_agent.py` whitelists entity labels and
  relationship types before anything reaches Neo4j's query builder, rather
  than trusting the LLM's output directly.
- **Evaluation** (`app/eval/run_evals.py`) - deterministic, non-LLM-judge
  evaluators per agent (research, fact-checker, graph-builder, changelog
  summarizer, Q&A, alerting), each with a small LangSmith dataset. Run with
  `python -m app.eval.run_evals [agent_name ...]`; requires `LANGCHAIN_API_KEY`.
- **Tracing** - every LLM call (`app/agents/llm.py::call_llm` /
  `call_llm_with_tools`) is wrapped in LangSmith's `@traceable`, tagged with
  a `step` name per agent, so a real pipeline run - not just an eval run -
  shows up in the LangSmith UI. No-ops cleanly with `LANGCHAIN_API_KEY` unset.
- **Structured logging** - every LLM call logs truncated input/output at
  INFO (`llm.steps` logger). The RAG pipeline logs chunk boundaries and
  retrieval hits separately (`rag` logger): chunk_start/chunk_end/index_write
  in `research_agent.py`, retrieve_start/retrieve_end in `analyst_agent.py`
  and `qa_agent.py`.

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
| `LANGCHAIN_API_KEY` | Optional — without it, tracing/evaluation are skipped (LLM calls still work normally) | Yes | https://smith.langchain.com/settings |

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

## Bonus features implemented

- **Sentiment scoring** — `app/services/sentiment.py`, tags Announcement nodes.
- **Real-time alerting** — `app/services/alerting.py`, pings Telegram immediately
  on high-severity events instead of waiting for the weekly cycle.
- **Interactive graph visualization** — Plotly network graph in Streamlit
  (`pages/3_Knowledge_Graph.py`) and a force-directed graph in Next.js
  (`components/GraphExplorer.tsx`), both reading `/api/v1/graph/snapshot`.
- **Dynamic Q&A** — `app/agents/qa_agent.py`, see Architecture above.
- **User-defined Tracked Topics** — `app/api/routes_topics.py`, replaces a
  previously hardcoded theme list for both the Analyst and Change-Log agents.
- **Guardrails, evaluation, and tracing** — see the dedicated section above.

## Notes / what to harden before production

- `POST /api/v1/graph/query` runs arbitrary Cypher — sandbox or remove before
  exposing publicly. (Note this is separate from the Q&A Agent's `graph_query`
  tool, which only accepts a whitelisted `question_type`, not raw Cypher.)
- `scrape_career_page` is a stub; wire it to each competitor's actual ATS API
  (Greenhouse/Lever/Ashby) rather than raw HTML scraping.
- Swap `voyageai` in `app/services/embeddings.py` for whatever embedding
  provider you standardize on; just keep the `embed_text`/`embed_documents`
  function signatures.
- Guardrails in this project are deliberately cheap/deterministic (regex +
  structural checks), not an LLM-as-judge — see `guardrails.py`'s docstring
  for the reasoning. Swap in a judge-based check for anything that needs
  semantic-level moderation, not just structural/PII/injection checks.
