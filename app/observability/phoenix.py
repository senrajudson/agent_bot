"""
Phoenix / OpenTelemetry observability.

Google ADK emits OpenTelemetry spans natively (gen_ai.* attributes) for
LlmAgent, Runner and tool calls, so Phoenix picks them up via
auto_instrument=True. LiteLLM calls are also instrumented via the OTel
HTTPX exporter for outbound HTTP.
"""

from phoenix.otel import register
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.core.config import settings


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

    return _tracer_provider


def instrument_fastapi_app(app):
    if not settings.PHOENIX_ENABLED:
        return

    FastAPIInstrumentor.instrument_app(app)
