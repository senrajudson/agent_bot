"""
Phoenix / OpenTelemetry observability.

Instruments:
- FastAPI (HTTP request/response spans)
- LiteLLM (LLM call spans via openinference-instrumentation-litellm)
- Google ADK native telemetry (agent, tool, LLM spans)
"""

import logging

from phoenix.otel import register
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from openinference.instrumentation.litellm import LiteLLMInstrumentor

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


def instrument_fastapi_app(app):
    if not settings.PHOENIX_ENABLED:
        return

    FastAPIInstrumentor.instrument_app(app)
