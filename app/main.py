import warnings

warnings.filterwarnings(
    "ignore",
    message=r".*PLUGGABLE_AUTH.*",
    category=UserWarning,
)

from fastapi import FastAPI

from app.core.config import settings
from app.observability.phoenix import (
    instrument_fastapi_app,
    setup_phoenix_tracing,
)


setup_phoenix_tracing()

from app.agent.orchestrator import process_message
from app.schemas.chat import ChatRequest, ChatResponse


app = FastAPI(title=settings.API_NAME)

instrument_fastapi_app(app)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": settings.API_NAME,
        "model": settings.OLLAMA_MODEL,
        "phoenix_enabled": settings.PHOENIX_ENABLED,
        "phoenix_project": settings.PHOENIX_PROJECT_NAME,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    return await process_message(payload)