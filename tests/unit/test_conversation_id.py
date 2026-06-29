"""Unit tests for ConversationId value object (Prompt 3 Ciclo 1)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.value_objects import ConversationId


class TestConversationIdConstruction:
    """C-1..C-3: Construction, validation, serialization."""

    def test_construct_with_string_exposes_value(self):
        cid = ConversationId("alice")
        assert cid.value == "alice"

    def test_str_returns_value(self):
        assert str(ConversationId("alice")) == "alice"

    def test_construct_rejects_empty_string(self):
        with pytest.raises(ValueError, match="non-empty"):
            ConversationId("")

    def test_construct_rejects_none(self):
        """AM-5: ConversationId(None) must raise a clear error."""
        with pytest.raises((TypeError, ValueError)) as exc_info:
            ConversationId(None)
        msg = str(exc_info.value).lower()
        assert "non-empty" in msg or "str" in msg


class TestFromUserId:
    """C-4..C-6: Factory from_user_id with various inputs."""

    def test_from_user_id_with_normal_string(self):
        assert ConversationId.from_user_id("alice") == ConversationId("alice")

    def test_from_user_id_with_none_returns_anonymous(self):
        assert ConversationId.from_user_id(None) == ConversationId("anonymous")

    def test_from_user_id_with_empty_string_returns_anonymous(self):
        assert ConversationId.from_user_id("") == ConversationId("anonymous")

    def test_from_user_id_preserves_underscores_and_dots(self):
        """PiTag-style or Google Chat IDs may contain these."""
        cid = ConversationId.from_user_id("users/u1")
        assert cid.value == "users/u1"


class TestImmutabilityAndEquality:
    """C-7..C-9: frozen semantics, equality, hash."""

    def test_two_cids_with_same_value_are_equal(self):
        assert ConversationId("alice") == ConversationId("alice")

    def test_two_cids_with_same_value_share_hash(self):
        assert hash(ConversationId("alice")) == hash(ConversationId("alice"))

    def test_cid_is_frozen(self):
        cid = ConversationId("alice")
        with pytest.raises(FrozenInstanceError):
            cid.value = "bob"  # type: ignore[misc]


class TestExports:
    """C-10: ConversationId is exported from app.domain."""

    def test_exported_from_domain_package(self):
        from app.domain import ConversationId as ExportedCID

        assert ExportedCID is ConversationId
