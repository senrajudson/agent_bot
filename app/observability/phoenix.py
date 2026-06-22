"""
Phoenix / OpenTelemetry observability.

Instruments:
- FastAPI (HTTP request/response spans) — via FastAPIInstrumentor
- LiteLLM (LLM call spans) — auto-instrumented by Phoenix register(auto_instrument=True)
- HTTPX (outbound HTTP spans — PI Web API, Qdrant, Grafana, MCP, Math Tool)
- ADK native telemetry (agent, tool spans) — uses the global TracerProvider automatically
"""

import logging

from phoenix.otel import register
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.core.config import settings


logger = logging.getLogger(__name__)

_tracer_provider = None


def setup_phoenix_tracing():
    global _tracer_provider

    if not settings.PHOENIX_ENABLED:
        return None

    if _tracer_provider is not None:
        return _tracer_provider

    # register() with auto_instrument=True auto-instruments all installed
    # OpenInference libraries (litellm, google_genai) via entry points.
    # This is enough for LLM spans — no manual LiteLLMInstrumentor call needed.
    _tracer_provider = register(
        project_name=settings.PHOENIX_PROJECT_NAME,
        endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
        protocol=settings.PHOENIX_PROTOCOL,
        auto_instrument=True,
        batch=False,
        verbose=False,
    )

    _instrument_httpx()

    return _tracer_provider


def _instrument_httpx():
    try:
        instrumentor = HTTPXClientInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
            logger.info("HTTPX instrumented successfully")
        else:
            logger.debug("HTTPX already instrumented")
    except Exception as e:
        logger.warning("Failed to instrument HTTPX: %s", e)


def instrument_fastapi_app(app):
    if not settings.PHOENIX_ENABLED:
        return

    FastAPIInstrumentor.instrument_app(app)
