# AGENTS.md

## What This Is

FastAPI chatbot API using LangChain agents. Routes messages through a classifier to specialized agents (general conversation, PI System queries). Uses Redis for conversation memory, Phoenix for tracing.

## Running

```bash
# Start dev server (API_PORT=8002 by default)
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

# Health check
curl http://localhost:8002/health

# Chat endpoint
curl -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "oi", "user_id": "test"}'
```

## Environment

Copy `.env.example` (if exists) to `.env`. Required vars:

- `LLM_PROVIDER`: `ollama` | `groq` | `openai_compatible`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`: Ollama config
- `GRAFANA_LOKI_QUERY_RANGE_URL`: Grafana Loki URL (required)
- `REDIS_URL`: Redis for chat memory (default: `redis://127.0.0.1:6379/2`)
- `PI_WEB_API_*`: PI System credentials (for PIMS route)

## Architecture

```
POST /chat → orchestrator.process_message()
  → load_memory (Redis)
  → OCR step (if images attached)
  → router (LLM classifies → conversa_comum | pims)
  → selected agent runs (general_agent | pi_agent)
  → save memory (Redis)
```

**Entry:** `app/main.py` → FastAPI app
**Orchestrator:** `app/agent/orchestrator.py` → main pipeline
**Router:** `app/agent/router.py` → LangChain chain with PydanticOutputParser
**Agents:** `app/agent/general_agent.py`, `app/agent/pi_agent.py`
**Tools:** `app/tools/` → LangChain @tool decorated functions
**Clients:** `app/clients/` → Redis, PI Web API, Grafana Loki, provider_client (LLM factory)
**Prompts:** `app/prompts/` → system prompts as Python strings
**Schemas:** `app/schemas/` → Pydantic models (ChatRequest, ChatResponse, LLMParams)

## Key Quirks

- **No tests, no linting, no CI** — verify changes manually via `/chat` endpoint
- **No requirements.txt or pyproject.toml** in repo — dependencies managed externally
- **LLM provider switch** is via `LLM_PROVIDER` env var; `provider_client.py:97` handles dispatch
- **PI agent tools** are registered in `app/agent/tools_registry.py:13-19`
- **Memory** is Redis-based, TTL 7 days, max 8 turns — key pattern `pi_chat:memory:{conversation_id}:turns`
- **Router fallback** returns `conversa_comum` on any parsing error
- **Portuguese throughout** — prompts, variable names, error messages are in pt-BR
