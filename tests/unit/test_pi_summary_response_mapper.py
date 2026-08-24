from domain.analysis.models import MetricSource
from domain.analysis.services.pi_summary_response_mapper import PiSummaryResponseMapper


def test_map_streamsets_summary_single_value():
    mapper = PiSummaryResponseMapper()
    payload = {
        "Items": [
            {
                "WebId": "W123",
                "Items": [
                    {
                        "Type": "Average",
                        "Value": {"Timestamp": "2026-01-01T00:00:00Z", "Value": 42.5, "Good": True},
                    },
                    {
                        "Type": "Maximum",
                        "Value": {"Timestamp": "2026-01-01T00:00:00Z", "Value": 100.0, "Good": True},
                    },
                ],
            }
        ]
    }
    web_id_map = {"W123": "TAG_01"}
    res = mapper.map_streamsets_summary(payload, web_id_map)
    assert len(res) == 2
    assert res[0].tag == "TAG_01"
    assert res[0].metric == "mean"
    assert res[0].value == 42.5
    assert res[0].source == MetricSource.PI_SUMMARY

    assert res[1].metric == "max"
    assert res[1].value == 100.0


def test_map_streamsets_summary_buckets_list():
    mapper = PiSummaryResponseMapper()
    payload = {
        "Items": [
            {
                "WebId": "W123",
                "Items": [
                    {
                        "Type": "Average",
                        "Value": [
                            {"Timestamp": "2026-01-01T00:00:00Z", "Value": 10.0, "Good": True},
                            {"Timestamp": "2026-01-01T01:00:00Z", "Value": 20.0, "Good": True},
                        ],
                    }
                ],
            }
        ]
    }
    web_id_map = {"W123": "TAG_01"}
    res = mapper.map_streamsets_summary(payload, web_id_map, interval="1h")
    assert len(res) == 2
    assert res[0].value == 10.0
    assert res[0].interval == "1h"
    assert res[1].value == 20.0
    assert res[1].interval == "1h"
