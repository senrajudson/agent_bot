"""
Phoenix / OpenTelemetry observability.

Instruments:
- FastAPI (HTTP request/response spans)
- LiteLLM (LLM call spans via openinference-instrumentation-litellm)
- Google GenAI (LLM spans from google.genai SDK used by ADK via openinference)
- HTTPX (outbound HTTP spans — PI Web API, Qdrant, Grafana, MCP, Math Tool)
- ADK native telemetry (agent, tool spans) uses the global TracerProvider automatically

Includes a custom SpanExporter wrapper that removes duplicate token count
attributes from wrapper/intermediary spans (call_llm, generate_content,
invoke_agent, etc.) before they reach the real OTLP exporter.  This
prevents the Phoenix UI from summing the same tokens across nested spans
(typically inflating them 3x).
"""

import logging
import os
import re

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from phoenix.otel import register
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from openinference.instrumentation.litellm import LiteLLMInstrumentor
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.core.config import settings


logger = logging.getLogger(__name__)

_tracer_provider = None

# ---------------------------------------------------------------------------
# Span names whose token attributes should be removed.
# ---------------------------------------------------------------------------
_EXACT_MATCH_NAMES: frozenset[str] = frozenset({
    "call_llm",
    "invoke_agent",
    "invocation",
    "agent",
    "chain",
})

_PREFIX_MATCH_NAMES: tuple[str, ...] = ("generate_content",)


def _is_wrapper_span(span_name: str) -> bool:
    """Return True if *span_name* refers to an ADK/OTel wrapper span
    whose token attributes duplicate the real LLM span (acompletion)."""
    if span_name in _EXACT_MATCH_NAMES:
        return True
    return any(span_name.startswith(p) for p in _PREFIX_MATCH_NAMES)


# ---------------------------------------------------------------------------
# Token-count attributes that should be removed from wrapper spans.
# Covers OpenInference semconv and OpenTelemetry GenAI semconv.
# ---------------------------------------------------------------------------
_TOKEN_ATTRS_TO_REMOVE: frozenset[str] = frozenset({
    # openinference-instrumentation-litellm
    "llm.token_count.prompt",
    "llm.token_count.completion",
    "llm.token_count.total",
    "llm.token_count.prompt_details.cache_read",
    "llm.token_count.prompt_details.cache_write",
    "llm.token_count.prompt_details.audio",
    "llm.token_count.prompt_details.cache_input",
    "llm.token_count.completion_details.reasoning",
    "llm.token_count.completion_details.audio",
    "llm.cost.completion_details.output",
    # OTel GenAI semconv (Google ADK)
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.total_tokens",
    "gen_ai.usage.completion_tokens",
    "gen_ai.usage.prompt_tokens",
    "gen_ai.usage.cache_creation_input_tokens",
    "gen_ai.usage.cache_read_input_tokens",
    "gen_ai.usage.experimental.reasoning_tokens",
    "gen_ai.usage.experimental.system_instruction_tokens",
})


def _sanitize_span(span) -> None:
    """Remove token-count attributes from a wrapper span in-place."""
    try:
        attrs = getattr(span, "_attributes", None)
        if not attrs:
            return
        if not _is_wrapper_span(getattr(span, "name", "")):
            return
        for key in _TOKEN_ATTRS_TO_REMOVE:
            attrs.pop(key, None)
    except Exception:
        # Never break the pipeline due to a telemetry helper.
        pass


# ---------------------------------------------------------------------------
# SpanExporter wrapper — sanitises spans before they reach the real exporter.
# ---------------------------------------------------------------------------
class _TokenDedupSpanExporter(SpanExporter):
    """Wraps a real SpanExporter and strips duplicate token attributes from
    wrapper/intermediary spans before serialisation.

    The Phoenix UI sums token usage from all descendant spans, which
    inflates the cumulative count (typically 3x for a single LLM call).

    This exporter walks every span in each batch and removes token
    attributes from wrapper spans so that only the innermost LLM span
    (``acompletion``) carries token counts.
    """

    def __init__(self, wrapped_exporter: SpanExporter) -> None:
        self._wrapped = wrapped_exporter

    def export(self, spans):
        try:
            for span in spans or ():
                _sanitize_span(span)
        except Exception:
            pass
        return self._wrapped.export(spans)

    def shutdown(self) -> None:
        try:
            return self._wrapped.shutdown()
        except Exception:
            return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return self._wrapped.force_flush(timeout_millis)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Wiring helper — finds the Phoenix SimpleSpanProcessor and wraps its exporter.
# ---------------------------------------------------------------------------
def _wrap_default_exporter(tracer_provider) -> None:
    """Replace the exporter inside the default SimpleSpanProcessor created by
    ``phoenix.otel.register()`` with a ``_TokenDedupSpanExporter`` wrapper.

    Idempotent: calling multiple times does not double-wrap.
    """
    try:
        active = tracer_provider._active_span_processor
    except AttributeError:
        return

    for sp in getattr(active, "_span_processors", ()) or ():
        exporter = getattr(sp, "span_exporter", None)
        if exporter is None:
            continue
        if isinstance(exporter, _TokenDedupSpanExporter):
            continue  # already wrapped
        sp.span_exporter = _TokenDedupSpanExporter(exporter)


# ---------------------------------------------------------------------------
# Excluded URLs — suppress noisy health-check spans from auxiliary services
# ---------------------------------------------------------------------------

def _configure_excluded_urls() -> None:
    """Configure OTel HTTP excluded URLs for httpx to suppress noisy
    health-check spans from auxiliary services (e.g. Qdrant root GET).

    The regex targets only the ROOT path of the Qdrant URL — vector
    search calls during /chat are NOT excluded.

    Reads ``QDRANT_URL`` from settings and sets
    ``OTEL_PYTHON_HTTPX_EXCLUDED_URLS`` before any instrumentor runs.
    """
    try:
        qdrant_url = (settings.QDRANT_URL or "").rstrip("/")
        if not qdrant_url:
            return

        # ^http://10\.247\.179\.197:6333/?$
        qdrant_root_regex = rf"^{re.escape(qdrant_url)}/?$"

        existing = os.environ.get("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", "").strip()
        merged = (
            qdrant_root_regex
            if not existing
            else f"{existing},{qdrant_root_regex}"
        )
        os.environ["OTEL_PYTHON_HTTPX_EXCLUDED_URLS"] = merged

        logger.info(
            "OTel HTTPX excluded URLs configured: %s",
            merged,
        )
    except Exception as exc:
        logger.warning("Failed to configure OTel excluded URLs: %s", exc)


# ---------------------------------------------------------------------------
# Public setup
# ---------------------------------------------------------------------------
def setup_phoenix_tracing():
    global _tracer_provider

    if not settings.PHOENIX_ENABLED:
        return None

    if _tracer_provider is not None:
        return _tracer_provider

    _configure_excluded_urls()

    _tracer_provider = register(
        project_name=settings.PHOENIX_PROJECT_NAME,
        endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
        protocol=settings.PHOENIX_PROTOCOL,
        auto_instrument=True,
        batch=False,
    )

    _wrap_default_exporter(_tracer_provider)

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


# ---------------------------------------------------------------------------
# Analysis tools metrics (OTel counters/histograms)
# ---------------------------------------------------------------------------
_analysis_duration_histogram = None
_analysis_gaps_counter = None
_analysis_spikes_counter = None
_analysis_quality_counter = None


def _get_analysis_metrics():
    global _analysis_duration_histogram, _analysis_gaps_counter
    global _analysis_spikes_counter, _analysis_quality_counter

    if _analysis_duration_histogram is not None:
        return (
            _analysis_duration_histogram,
            _analysis_gaps_counter,
            _analysis_spikes_counter,
            _analysis_quality_counter,
        )

    try:
        from opentelemetry import metrics

        meter = metrics.get_meter("agent_bot.analysis")

        _analysis_duration_histogram = meter.create_histogram(
            name="analysis.duration_ms",
            description="Duration of analysis operations in milliseconds",
            unit="ms",
        )
        _analysis_gaps_counter = meter.create_counter(
            name="analysis.gaps.count",
            description="Number of gaps detected",
            unit="1",
        )
        _analysis_spikes_counter = meter.create_counter(
            name="analysis.spikes.count",
            description="Number of spikes detected",
            unit="1",
        )
        _analysis_quality_counter = meter.create_counter(
            name="analysis.quality.verdict",
            description="Quality verdict distribution",
            unit="1",
        )

        return (
            _analysis_duration_histogram,
            _analysis_gaps_counter,
            _analysis_spikes_counter,
            _analysis_quality_counter,
        )
    except Exception as e:
        logger.debug("Failed to create analysis metrics: %s", e)
        return None, None, None, None


def record_analysis_metrics(
    *,
    tool_name: str,
    duration_ms: float,
    gaps_count: int = 0,
    spikes_count: int = 0,
    verdict: str = "",
    tags_count: int = 1,
) -> None:
    """Record analysis metrics for observeability."""
    h, gc, sc, vc = _get_analysis_metrics()
    if h is None:
        return

    attrs = {"tool": tool_name, "tags_count": str(tags_count)}
    h.record(duration_ms, attributes=attrs)

    if gaps_count > 0:
        gc.add(gaps_count, attributes={"tool": tool_name, "method": "interpolated"})

    if spikes_count > 0:
        sc.add(spikes_count, attributes={"tool": tool_name, "basis": "mixed"})

    if verdict:
        vc.add(1, attributes={"tool": tool_name, "verdict": verdict})
