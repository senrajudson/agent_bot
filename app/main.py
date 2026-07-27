import os

from fastapi import FastAPI, Request

from app.core.config import settings
from app.core.lifespan import event_driven_lifespan
from app.core.runtime_publisher import build_runtime_event_publisher
from app.observability.phoenix import (
    instrument_fastapi_app,
    setup_phoenix_tracing,
)


def _inject_llm_env() -> None:
    """Injeta credenciais LLM do Pydantic Settings em os.environ.

    O ``google.adk.models.google_llm.Gemini`` (ADK) NÃO repassa o
    ``api_key`` recebido no construtor para ``google.genai.Client``.
    O genai lê a chave exclusivamente de ``GOOGLE_API_KEY`` /
    ``GEMINI_API_KEY`` no ambiente do processo.  Sem esta injeção o ADK
    ignora ``settings.GEMINI_API_KEY`` e falha com
    ``ValueError: No API key was provided``.
    """
    pairs = (
        ("GEMINI_API_KEY", settings.GEMINI_API_KEY),
        ("GOOGLE_API_KEY", settings.GEMINI_API_KEY),
        ("GROQ_API_KEY", settings.GROQ_API_KEY),
        ("OPENAI_COMPATIBLE_API_KEY", settings.OPENAI_COMPATIBLE_API_KEY),
    )
    for env_name, value in pairs:
        if value and not os.environ.get(env_name):
            os.environ[env_name] = value


_inject_llm_env()

setup_phoenix_tracing()

from domain.core.config import configure_domain_settings

configure_domain_settings(settings.to_domain_integration_settings())

from app.agent.orchestrator import process_message
from app.schemas.chat import ChatRequest, ChatResponse


app = FastAPI(title=settings.API_NAME, lifespan=event_driven_lifespan)

instrument_fastapi_app(app)

if settings.ENABLE_ARTIFACTS:
    from app.api.artifacts import router as artifacts_router
    from app.api.artifacts_upload import router as artifacts_upload_router
    app.include_router(
        artifacts_router,
        prefix=settings.AGENT_ARTIFACTS_PUBLIC_PATH_PREFIX,
    )
    app.include_router(
        artifacts_upload_router,
        prefix=settings.AGENT_ARTIFACTS_PUBLIC_PATH_PREFIX,
    )


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
async def chat(payload: ChatRequest, request: Request):
    pool = getattr(request.app.state, "postgres_pool", None)
    publisher = build_runtime_event_publisher(pool, settings)
    return await process_message(payload, event_publisher=publisher)