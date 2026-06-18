"""
Phoenix / OpenTelemetry observability.

Instruments:
- FastAPI (HTTP request/response spans)
- LiteLLM (LLM call spans via openinference-instrumentation-litellm)
- Google GenAI (LLM spans from google.genai SDK used by ADK via openinference)
- HTTPX (outbound HTTP spans — PI Web API, Qdrant, Grafana, MCP, Math Tool)
- ADK native telemetry (agent, tool spans) uses the global TracerProvider automatically
"""

import logging

from phoenix.otel import register
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from openinference.instrumentation.litellm import LiteLLMInstrumentor
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
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

    _tracer_provider = register(
        project_name=settings.PHOENIX_PROJECT_NAME,
        endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
        protocol=settings.PHOENIX_PROTOCOL,
        auto_instrument=True,
        batch=False,
    )

    _instrument_litellm()
    _instrument_google_genai()
    _instrument_httpx()

    return _tracer_provider


def _instrument_litellm():
    try:
        instrumentor = LiteLLMInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
            logger.info("LiteLLM instrumented successfully")
        else:
            logger.debug("LiteLLM already instrumented")
    except Exception as e:
        logger.warning("Failed to instrument LiteLLM: %s", e)


def _instrument_google_genai():
    try:
        instrumentor = GoogleGenAIInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
            logger.info("Google GenAI instrumented successfully")
        else:
            logger.debug("Google GenAI already instrumented")
    except Exception as e:
        logger.warning("Failed to instrument Google GenAI: %s", e)


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
