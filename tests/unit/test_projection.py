"""Tests for ConversationMemoryProjection."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.projections import (
    AssistantMessageRecorded,
    ConversationMemoryProjection,
    ConversationTurn,
    UserMessageRecorded,
    format_turns_for_prompt,
)


# =========================================================================
# ConversationTurn
# =========================================================================
class TestConversationTurn:
    def test_frozen(self) -> None:
        turn = ConversationTurn(role="user", content="hi", created_at="2026-01-01T00:00:00")
        with pytest.raises(FrozenInstanceError):
            turn.content = "bye"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        turn = ConversationTurn(role="assistant", content="hello", created_at="now", metadata={"a": 1})
        d = turn.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "hello"
        assert d["metadata"] == {"a": 1}


# =========================================================================
# ConversationMemoryProjection
# =========================================================================
class TestProjection:
    def test_starts_empty(self) -> None:
        proj = ConversationMemoryProjection(conversation_id="c1")
        assert proj.project() == []

    def test_apply_user_message(self) -> None:
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(UserMessageRecorded(content="hi", created_at="now"))
        # User message is buffered, not yet in turns
        assert proj.project() == []

    def test_apply_assistant_without_pending_user(self) -> None:
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(AssistantMessageRecorded(content="hello", created_at="now"))
        turns = proj.project()
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == ""  # no pending user
        assert turns[1].role == "assistant"
        assert turns[1].content == "hello"

    def test_apply_user_then_assistant(self) -> None:
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(UserMessageRecorded(content="hi", created_at="2026-01-01"))
        proj.apply(AssistantMessageRecorded(content="hello", created_at="2026-01-02"))
        turns = proj.project()
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == "hi"
        assert turns[0].created_at == "2026-01-01"
        assert turns[1].role == "assistant"
        assert turns[1].content == "hello"
        assert turns[1].created_at == "2026-01-02"

    def test_multiple_pairs_preserve_order(self) -> None:
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(UserMessageRecorded(content="m1", created_at="t1"))
        proj.apply(AssistantMessageRecorded(content="r1", created_at="t2"))
        proj.apply(UserMessageRecorded(content="m2", created_at="t3"))
        proj.apply(AssistantMessageRecorded(content="r2", created_at="t4"))
        turns = proj.project()
        assert len(turns) == 4
        assert turns[0].content == "m1"
        assert turns[1].content == "r1"
        assert turns[2].content == "m2"
        assert turns[3].content == "r2"

    def test_project_returns_copy(self) -> None:
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(UserMessageRecorded(content="m", created_at="t"))
        proj.apply(AssistantMessageRecorded(content="r", created_at="t2"))
        t1 = proj.project()
        t2 = proj.project()
        assert t1 is not t2
        assert len(t1) == len(t2)

    def test_ignore_unknown_event_type(self) -> None:
        from app.domain.events import DomainEvent

        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(DomainEvent())  # should not crash
        assert proj.project() == []

    def test_duplicate_user_messages_overwrite_pending_user_without_turn(self) -> None:
        """Caracterização do estado atual: UserMessageRecorded duplicado sobrescreve
        o pending user sem gerar turn.

        Não é necessariamente comportamento ideal — congelado para detectar mudanças.
        """
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(UserMessageRecorded(content="user1", created_at="t1"))
        proj.apply(UserMessageRecorded(content="user2", created_at="t2"))
        turns = proj.project()
        assert turns == []
        assert len(turns) == 0

    def test_duplicate_assistant_messages_create_empty_user_turns(self) -> None:
        """Caracterização do estado atual: AssistantMessageRecorded sem
        UserMessageRecorded prévio gera user turn vazio.

        Duplicar AssistantMessageRecorded gera 4 turns (2 user vazios + 2 assistant).
        Comportamento não-intuitivo congelado, não corrigido.
        """
        proj = ConversationMemoryProjection(conversation_id="c1")
        proj.apply(AssistantMessageRecorded(content="asst1", created_at="t1"))
        proj.apply(AssistantMessageRecorded(content="asst2", created_at="t2"))
        turns = proj.project()
        assert len(turns) == 4
        assert turns[0].role == "user"
        assert turns[0].content == ""
        assert turns[1].role == "assistant"
        assert turns[1].content == "asst1"
        assert turns[2].role == "user"
        assert turns[2].content == ""
        assert turns[3].role == "assistant"
        assert turns[3].content == "asst2"


# =========================================================================
# format_turns_for_prompt
# =========================================================================
class TestFormatTurnsForPrompt:
    def test_empty_turns(self) -> None:
        assert format_turns_for_prompt([]) == ""

    def test_single_user_turn(self) -> None:
        turns = [ConversationTurn(role="user", content="hi", created_at="t")]
        result = format_turns_for_prompt(turns)
        assert "> Usuário: hi" in result
        assert "Contexto recente" in result

    def test_user_and_assistant(self) -> None:
        turns = [
            ConversationTurn(role="user", content="question", created_at="t1"),
            ConversationTurn(role="assistant", content="answer", created_at="t2"),
        ]
        result = format_turns_for_prompt(turns)
        assert "> Usuário: question" in result
        assert "> Assistente: answer" in result

    def test_empty_content_skipped(self) -> None:
        turns = [ConversationTurn(role="user", content="", created_at="t")]
        result = format_turns_for_prompt(turns)
        assert "> Usuário:" not in result

    def test_output_matches_legacy(self) -> None:
        """Verify output matches the legacy format_memory_for_prompt output."""
        from app.services.chat_memory_service import ChatMemoryTurn, format_memory_for_prompt

        legacy_turns = [
            ChatMemoryTurn(role="user", content="hello", created_at="2026-01-01", metadata={}),
            ChatMemoryTurn(role="assistant", content="hi", created_at="2026-01-02", metadata={}),
        ]
        new_turns = [
            ConversationTurn(role="user", content="hello", created_at="2026-01-01", metadata={}),
            ConversationTurn(role="assistant", content="hi", created_at="2026-01-02", metadata={}),
        ]

        legacy_output = format_memory_for_prompt(legacy_turns)
        new_output = format_turns_for_prompt(new_turns)
        assert legacy_output == new_output
