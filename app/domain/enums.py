"""Domain enums — values match the PI Web API / Agent Bot vocabulary."""
from __future__ import annotations

from enum import Enum


class PointType(str, Enum):
    """Type of a PI Point."""

    DIGITAL = "Digital"
    ANALOG = "analog"
    STRING = "String"


class TemporalDataMethod(str, Enum):
    """Method for fetching temporal data."""

    RECORDED = "recorded"
    INTERPOLATED = "interpolated"
    SUMMARY = "summary"


class CalculusOperation(str, Enum):
    """Temporal calculus operations."""

    INTEGRAL = "integral"
    DERIVATIVE = "derivative"


class StatisticalOperation(str, Enum):
    """Statistical operations on a series."""

    MEAN = "mean"
    MAX = "max"
    MIN = "min"
    SUM = "sum"
    COUNT = "count"
    MEDIAN = "median"
    RANGE = "range"
    VARIANCE_POPULATION = "variance_population"
    VARIANCE_SAMPLE = "variance_sample"
    STDDEV_POPULATION = "stddev_population"
    STDDEV_SAMPLE = "stddev_sample"


class AgentRoute(str, Enum):
    """Route chosen by the agent router."""

    GENERAL_CHAT = "conversa_comum"
    CALCULATOR = "calculadora"
    PIMS = "pims"


class AggregateType(str, Enum):
    """Logical aggregate type for domain events."""

    CONVERSATION = "Conversation"
    AGENT_RUN = "AgentRun"
    GOOGLE_CHAT_MESSAGE = "GoogleChatMessage"
    PI_TAG_QUERY = "PiTagQuery"
