from __future__ import annotations

import logging
from typing import Any

from domain.analysis.models import BucketSummaryResult, MetricSource

logger = logging.getLogger("domain.analysis.pi_summary_response_mapper")

_SUMMARY_TYPE_TO_METRIC = {
    "Average": "mean",
    "Minimum": "min",
    "Maximum": "max",
    "Count": "count",
    "StdDev": "stddev_sample",
    "PopulationStdDev": "stddev_pop",
    "Range": "range",
    "PercentGood": "percent_good",
    "Total": "sum",
}


class PiSummaryResponseMapper:
    def map_streamsets_summary(
        self,
        payload: dict[str, Any],
        web_id_to_tag: dict[str, str],
        calculation_basis: str = "TimeWeighted",
        interval: str | None = None,
    ) -> list[BucketSummaryResult]:
        results: list[BucketSummaryResult] = []
        items = payload.get("Items", [])

        for item in items:
            web_id = item.get("WebId", "")
            tag = web_id_to_tag.get(web_id, web_id)
            summaries = item.get("Items", [])

            for s in summaries:
                st_type = s.get("Type", "")
                metric_name = _SUMMARY_TYPE_TO_METRIC.get(st_type, st_type.lower())
                
                # O resultado de um summary pode ser um dicionário Value (ex: {"Timestamp": "...", "Value": 12.3, "Good": True})
                # ou uma lista de buckets se summaryDuration foi passado
                val_data = s.get("Value")
                if isinstance(val_data, dict):
                    ts = val_data.get("Timestamp", "")
                    raw_val = val_data.get("Value")
                    good = bool(val_data.get("Good", True))
                    
                    float_val = None
                    if isinstance(raw_val, (int, float)):
                        float_val = float(raw_val)
                    elif isinstance(raw_val, dict) and "Value" in raw_val:
                        v = raw_val.get("Value")
                        if isinstance(v, (int, float)):
                            float_val = float(v)

                    results.append(
                        BucketSummaryResult(
                            tag=tag,
                            web_id=web_id,
                            metric=metric_name,
                            value=float_val,
                            timestamp=ts,
                            bucket_start=ts,
                            source=MetricSource.PI_SUMMARY,
                            summary_type=st_type,
                            calculation_basis=calculation_basis,
                            interval=interval,
                            good=good,
                        )
                    )
                elif isinstance(val_data, list):
                    for b in val_data:
                        if isinstance(b, dict):
                            ts = b.get("Timestamp", "")
                            raw_val = b.get("Value")
                            good = bool(b.get("Good", True))
                            float_val = float(raw_val) if isinstance(raw_val, (int, float)) else None
                            
                            results.append(
                                BucketSummaryResult(
                                    tag=tag,
                                    web_id=web_id,
                                    metric=metric_name,
                                    value=float_val,
                                    timestamp=ts,
                                    bucket_start=ts,
                                    source=MetricSource.PI_SUMMARY,
                                    summary_type=st_type,
                                    calculation_basis=calculation_basis,
                                    interval=interval,
                                    good=good,
                                )
                            )

        return results
