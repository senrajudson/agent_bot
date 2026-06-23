"""Tests for tag_extractor utility (pures, no I/O)."""
from __future__ import annotations

import pytest

from domain.pims.utils.tag_extractor import extract_tags_from_text, merge_unique_tags


# =========================================================================
# extract_tags_from_text
# =========================================================================
class TestExtractTagsFromText:
    def test_extracts_known_prefixes(self) -> None:
        text = "A tag UTI_XXX e ACI_YYY estao ok"
        tags = extract_tags_from_text(text)
        assert "UTI_XXX" in tags
        assert "ACI_YYY" in tags

    def test_extracts_red_prefix(self) -> None:
        tags = extract_tags_from_text("RED_ABC123")
        assert "RED_ABC123" in tags

    def test_extracts_lfs_prefix(self) -> None:
        tags = extract_tags_from_text("LFS_RB3_VAZ_GN_TOTAL")
        assert "LFS_RB3_VAZ_GN_TOTAL" in tags

    def test_extracts_lfi_prefix(self) -> None:
        tags = extract_tags_from_text("LFI_RB3_VAZ_GN_TOTAL")
        assert "LFI_RB3_VAZ_GN_TOTAL" in tags

    def test_extracts_cpd_prefix(self) -> None:
        tags = extract_tags_from_text("CPD_123")
        assert "CPD_123" in tags

    def test_extracts_ltq_prefix(self) -> None:
        tags = extract_tags_from_text("LTQ_456")
        assert "LTQ_456" in tags

    def test_extracts_sin_prefix(self) -> None:
        tags = extract_tags_from_text("SIN_ABC123")
        assert "SIN_ABC123" in tags

    def test_extracts_cdt_prefix(self) -> None:
        tags = extract_tags_from_text("CDT_ABC123")
        assert "CDT_ABC123" in tags

    def test_no_tags_returns_empty(self) -> None:
        tags = extract_tags_from_text("hello world no tags here")
        assert tags == []

    def test_empty_string_returns_empty(self) -> None:
        assert extract_tags_from_text("") == []

    def test_none_returns_empty(self) -> None:
        assert extract_tags_from_text(None) == []

    def test_extracts_multiple_tags(self) -> None:
        text = "Tags: UTI_123, ACI_456, LFS_789"
        tags = extract_tags_from_text(text)
        assert len(tags) == 3
        assert "UTI_123" in tags
        assert "ACI_456" in tags
        assert "LFS_789" in tags

    def test_preserves_underscore_suffix(self) -> None:
        tags = extract_tags_from_text("UTI_XX_YY_ZZ")
        assert "UTI_XX_YY_ZZ" in tags

    def test_does_not_extract_invalid_prefix(self) -> None:
        tags = extract_tags_from_text("XXX_123 FOO_456")
        assert tags == []

    def test_case_insensitive(self) -> None:
        """Regex is case-insensitive (re.IGNORECASE) — lowercase inputs match."""
        tags = extract_tags_from_text("uti_123")
        assert tags == ["UTI_123"]

    def test_extracted_tags_are_unique(self) -> None:
        text = "UTI_123 e UTI_123 novamente"
        tags = extract_tags_from_text(text)
        assert tags.count("UTI_123") == 1


# =========================================================================
# merge_unique_tags
# =========================================================================
class TestMergeUniqueTags:
    def test_merges_unique(self) -> None:
        result = merge_unique_tags(["A", "B"], ["C", "D"])
        assert result == ["A", "B", "C", "D"]

    def test_deduplicates(self) -> None:
        result = merge_unique_tags(["A", "B"], ["B", "C"])
        assert result == ["A", "B", "C"]

    def test_preserves_order(self) -> None:
        result = merge_unique_tags(["C", "A"], ["B", "A"])
        assert result == ["C", "A", "B"]

    def test_empty_lists(self) -> None:
        assert merge_unique_tags([], []) == []

    def test_single_list(self) -> None:
        assert merge_unique_tags(["X", "X", "Y"]) == ["X", "Y"]
