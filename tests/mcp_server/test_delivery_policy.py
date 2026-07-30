import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.output_delivery_policy import DefaultOutputDeliveryPolicy
from mcp_server.services.delivery.contracts import DeliveryMode


@pytest.fixture
def policy():
    return DefaultOutputDeliveryPolicy(
        inline_max_rows=100,
        inline_max_items=100,
        inline_max_bytes=65536,
        consultar_tag_artifact_max=20,
        consultar_tag_hard_cap=50,
    )


class TestTagStatistics:
    def test_series_drive_artifact(self, policy):
        d = policy.decide(tool_name="tag_statistics", output_mode="series")
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT
        assert d.reason == "output_mode=series"

    def test_scalar_inline(self, policy):
        d = policy.decide(tool_name="tag_statistics", output_mode="scalar")
        assert d.mode == DeliveryMode.INLINE

    def test_no_output_mode_inline(self, policy):
        d = policy.decide(tool_name="tag_statistics")
        assert d.mode == DeliveryMode.INLINE


class TestTagCalculus:
    def test_scalar_inline(self, policy):
        d = policy.decide(tool_name="tag_calculus")
        assert d.mode == DeliveryMode.INLINE

    def test_series_drive_artifact(self, policy):
        d = policy.decide(tool_name="tag_calculus", output_mode="series")
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT


class TestConsultarTag:
    def test_within_cap_inline(self, policy):
        d = policy.decide(tool_name="consultar_tag", tags_count=5)
        assert d.mode == DeliveryMode.INLINE

    def test_at_cap_inline(self, policy):
        d = policy.decide(tool_name="consultar_tag", tags_count=20)
        assert d.mode == DeliveryMode.INLINE

    def test_exceeds_cap_artifact(self, policy):
        d = policy.decide(tool_name="consultar_tag", tags_count=21)
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT
        assert d.reason_code == "TAG_COUNT_ARTIFACT"

    def test_exceeds_hard_cap_reject(self, policy):
        d = policy.decide(tool_name="consultar_tag", tags_count=51)
        assert d.mode == DeliveryMode.REJECT
        assert d.reason_code == "TAG_COUNT_EXCEEDED"

    def test_at_50_artifact(self, policy):
        d = policy.decide(tool_name="consultar_tag", tags_count=50)
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT


class TestSearchPiPoints:
    def test_inline(self, policy):
        d = policy.decide(tool_name="search_pi_points")
        assert d.mode == DeliveryMode.INLINE


class TestTagAttributesTool:
    def test_inline(self, policy):
        d = policy.decide(tool_name="tag_attributes_tool")
        assert d.mode == DeliveryMode.INLINE


class TestSafetyLimits:
    def test_row_count_exceeds(self, policy):
        d = policy.decide(tool_name="some_tool", row_count=101)
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT
        assert "row_count" in d.reason

    def test_row_count_within(self, policy):
        d = policy.decide(tool_name="some_tool", row_count=99)
        assert d.mode == DeliveryMode.INLINE

    def test_tags_count_exceeds(self, policy):
        d = policy.decide(tool_name="some_tool", tags_count=101)
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT

    def test_serialized_size_exceeds(self, policy):
        d = policy.decide(tool_name="some_tool", serialized_size=65537)
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT

    def test_serialized_size_within(self, policy):
        d = policy.decide(tool_name="some_tool", serialized_size=1000)
        assert d.mode == DeliveryMode.INLINE


class TestDeterminism:
    def test_same_input_same_output(self, policy):
        d1 = policy.decide(tool_name="tag_statistics", output_mode="series")
        d2 = policy.decide(tool_name="tag_statistics", output_mode="series")
        assert d1.mode == d2.mode
        assert d1.reason == d2.reason

    def test_semantic_overrides_safety(self, policy):
        d = policy.decide(tool_name="tag_statistics", output_mode="series", row_count=5)
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT
