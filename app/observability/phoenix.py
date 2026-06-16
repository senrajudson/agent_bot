"""
Phoenix / OpenTelemetry observability.

Google ADK emits OpenTelemetry spans natively (gen_ai.* attributes) for
LlmAgent, Runner and tool calls. To get rich traces (prompt, response,
token counts, tool definitions) in Phoenix's UI, we install the
OpenInference instrumentors that translate OTel spans into the
OpenInference format Phoenix knows how to render.

  - openinference-instrumentation-google-genai  → Gemini + ADK's google-genai usage
  - openinference-instrumentation-litellm       → LiteLlm (ADK) + direct litellm calls
"""

import logging

from phoenix.otel import register
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.core.config import settings


logger = logging.getLogger(__name__)


_tracer_provider = None
_instrumented = False


def setup_phoenix_tracing():
    global _tracer_provider, _instrumented

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

    if not _instrumented:
        _instrumented = True
        _instrument_openinference()

    return _tracer_provider


def _instrument_openinference() -> None:
    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        GoogleGenAIInstrumentor().instrument()
        logger.info("OpenInference: google_genai instrumented")
    except Exception as e:
        logger.warning("Failed to instrument google_genai: %s", e)

    try:
        from openinference.instrumentation.litellm import LiteLLMInstrumentor

        LiteLLMInstrumentor().instrument()
        logger.info("OpenInference: litellm instrumented")
    except Exception as e:
        logger.warning("Failed to instrument litellm: %s", e)


def instrument_fastapi_app(app):
    if not settings.PHOENIX_ENABLED:
        return

    FastAPIInstrumentor.instrument_app(app)
