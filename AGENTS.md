# Agent Bot - OpenCode Instructions

## Project Overview
FastAPI-based chat API with multi-agent routing (Ollama LLMs) and a separate math tool service. Uses Phoenix for observability, Redis for chat memory.

## Quick Start
```bash
# Install deps (uses Poetry)
poetry install

# Start services (Phoenix + Math Tool)
docker-compose up -d

# Run API (port 8002)
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8002
```

## Environment
- Copy `.env.example` to `.env` (or use existing `.env`)
- Required: `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `GRAFANA_LOKI_QUERY_RANGE_URL`, `GRAFANA_BEARER_TOKEN`
- Optional: `GROQ_API_KEY`, `OPENAI_COMPATIBLE_*`, `PI_WEB_API_*`, `PHOENIX_ENABLED`

## Architecture
```
app/
├── main.py              # FastAPI entrypoint, /chat endpoint
├── core/config.py       # Pydantic Settings (loads .env)
├── agent/
│   ├── orchestrator.py  # Main flow: route → agent → memory
│   ├── router.py        # Routes to "conversa_comum" or "pims"
│   ├── general_agent.py # General conversation
│   ├── pi_agent.py      # PIMS/PI Web API queries
│   └── tools_registry.py
├── services/            # Business logic (chat_memory, math_tool, consultar_tag, status_pims)
├── clients/             # External APIs (redis, ollama, grafana, pi_web_api, math_tool, qdrant)
├── tools/               # Agent tools (calculator, tag_statistics, tag_calculus, status_pims)
├── schemas/             # Pydantic models
├── prompts/             # Agent prompts
├── tasks/               # Background tasks (OCR)
├── utils/               # Helpers (math, time, formatting)
└── observability/       # Phoenix tracing setup
```

## Key Commands
```bash
# Run API
poetry run uvicorn app.main:app --reload --port 8002

# Run Math Tool (separate service, port 8001)
cd calc && poetry run uvicorn app.main:app --reload --port 8001

# Lint/Format (if configured)
poetry run ruff check .
poetry run ruff format .

# Type check (if configured)
poetry run mypy .
```

## Agent Flow
1. `/chat` receives `ChatRequest` (message, images, user_id, conversation_id)
2. `orchestrator.process_message` → `run_agent`
3. Load Redis memory → OCR images (if any) → Route via LLM
4. Route to `general_agent` or `pi_agent` (calculator_agent commented out)
5. Save turn to Redis memory → Return `ChatResponse`

## External Dependencies
- **Ollama** (default): `http://localhost:11434` with model `gemma4:e4b`
- **Phoenix** (observability): `http://localhost:6006` (docker-compose)
- **Redis**: `redis://127.0.0.1:6379/2` (chat memory)
- **Math Tool**: `http://localhost:8001` (docker-compose)
- **Grafana Loki**: For PIMS status queries
- **PI Web API**: For PIMS tag data

## Testing
No test suite currently exists. Add tests in `tests/` if needed.

## Common Issues
- Ensure Ollama is running with the configured model
- Phoenix collector must be accessible for tracing (`PHOENIX_ENABLED=true`)
- Redis must be available for chat memory
- Math Tool service must be running for calculator features