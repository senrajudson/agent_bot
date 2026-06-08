from typing import Literal


StatsOperation = Literal[
    "count",
    "sum",
    "mean",
    "median",
    "min",
    "max",
    "range",
    "variance_population",
    "variance_sample",
    "stddev_population",
    "stddev_sample",
]


CalculusOperation = Literal[
    "integral",
    "derivative",
]


TimeUnit = Literal[
    "second",
    "minute",
    "hour",
    "none",
]


TemporalDataMethod = Literal[
    "recorded",
    "interpolated",
    "summary",
]


SummaryType = Literal[
    "Average",
    "Minimum",
    "Maximum",
    "Range",
    "StdDev",
    "Total",
    "Count",
]


CalculationBasis = Literal[
    "TimeWeighted",
    "EventWeighted",
]