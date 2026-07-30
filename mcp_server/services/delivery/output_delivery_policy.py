from typing import Protocol

from mcp_server.services.delivery.contracts import DeliveryDecision, DeliveryMode


class OutputDeliveryPolicy(Protocol):
    def decide(
        self,
        *,
        tool_name: str,
        operation: str = "",
        output_mode: str | None = None,
        row_count: int | None = None,
        serialized_size: int | None = None,
        tags_count: int | None = None,
    ) -> DeliveryDecision: ...


class DefaultOutputDeliveryPolicy:
    def __init__(
        self,
        inline_max_rows: int = 100,
        inline_max_items: int = 100,
        inline_max_bytes: int = 65_536,
        consultar_tag_artifact_max: int = 20,
        consultar_tag_hard_cap: int = 50,
    ) -> None:
        self._inline_max_rows = inline_max_rows
        self._inline_max_items = inline_max_items
        self._inline_max_bytes = inline_max_bytes
        self._consultar_tag_artifact_max = consultar_tag_artifact_max
        self._consultar_tag_hard_cap = consultar_tag_hard_cap

    def decide(
        self,
        *,
        tool_name: str,
        operation: str = "",
        output_mode: str | None = None,
        row_count: int | None = None,
        serialized_size: int | None = None,
        tags_count: int | None = None,
    ) -> DeliveryDecision:
        tool = tool_name.strip().lower()

        # ──tag_statistics series (semântico, precedência 1) ──
        if tool == "tag_statistics":
            if output_mode == "series" or operation in ("series",):
                return DeliveryDecision(
                    mode=DeliveryMode.DRIVE_ARTIFACT,
                    reason="output_mode=series",
                    reason_code="SERIES_OUTPUT",
                    suggested_format="csv",
                )

        # ──tag_calculus series (futuro, semântico) ──
        if tool == "tag_calculus":
            if output_mode == "series":
                return DeliveryDecision(
                    mode=DeliveryMode.DRIVE_ARTIFACT,
                    reason="output_mode=series",
                    reason_code="SERIES_OUTPUT",
                    suggested_format="csv",
                )

        # ──consultar_tag: 1-20 INLINE, 21-50 DRIVE_ARTIFACT, >50 REJECT ──
        if tool == "consultar_tag":
            if tags_count is not None and tags_count > self._consultar_tag_hard_cap:
                return DeliveryDecision(
                    mode=DeliveryMode.REJECT,
                    reason=f"tags={tags_count} > hard cap {self._consultar_tag_hard_cap}",
                    reason_code="TAG_COUNT_EXCEEDED",
                )
            if tags_count is not None and tags_count > self._consultar_tag_artifact_max:
                return DeliveryDecision(
                    mode=DeliveryMode.DRIVE_ARTIFACT,
                    reason=f"tags={tags_count} > {self._consultar_tag_artifact_max}",
                    reason_code="TAG_COUNT_ARTIFACT",
                    suggested_format="csv",
                )

        # ──tag_attributes_tool: retorno grande ──
        if tool == "tag_attributes_tool":
            if serialized_size is not None and serialized_size > self._inline_max_bytes:
                return DeliveryDecision(
                    mode=DeliveryMode.DRIVE_ARTIFACT,
                    reason=f"serialized_size={serialized_size} > {self._inline_max_bytes}",
                    reason_code="BYTE_LIMIT_EXCEEDED",
                    suggested_format="csv",
                )

        # ──generate_pi_tags_series_csv: sempre DRIVE_ARTIFACT ──
        if tool == "generate_pi_tags_series_csv":
            return DeliveryDecision(
                mode=DeliveryMode.DRIVE_ARTIFACT,
                reason="series_csv_output",
                reason_code="SERIES_CSV_OUTPUT",
                suggested_format="csv",
            )

        # ──search_pi_points: sempre INLINE (cap 5 no service) ──
        if tool == "search_pi_points":
            return DeliveryDecision(
                mode=DeliveryMode.INLINE,
                reason="search_pi_points_hard_cap",
                reason_code="COMPACT_SCALAR",
            )

        # ──Segurança secundária (precedência 2) ──
        if row_count is not None and row_count > self._inline_max_rows:
            return DeliveryDecision(
                mode=DeliveryMode.DRIVE_ARTIFACT,
                reason=f"row_count={row_count} > {self._inline_max_rows}",
                reason_code="ROW_LIMIT_EXCEEDED",
                suggested_format="csv",
            )
        if tags_count is not None and tags_count > self._inline_max_items:
            return DeliveryDecision(
                mode=DeliveryMode.DRIVE_ARTIFACT,
                reason=f"tags_count={tags_count} > {self._inline_max_items}",
                reason_code="ITEM_LIMIT_EXCEEDED",
                suggested_format="csv",
            )
        if serialized_size is not None and serialized_size > self._inline_max_bytes:
            return DeliveryDecision(
                mode=DeliveryMode.DRIVE_ARTIFACT,
                reason=f"serialized_size={serialized_size} > {self._inline_max_bytes}",
                reason_code="BYTE_LIMIT_EXCEEDED",
                suggested_format="csv",
            )

        return DeliveryDecision(
            mode=DeliveryMode.INLINE,
            reason="default_inline",
            reason_code="COMPACT_SCALAR",
        )
