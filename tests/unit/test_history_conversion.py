"""ChatMessage → ModelMessage conversion for multi-turn context."""

from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from worker.src.dtos import ChatMessage
from worker.src.workflow import _to_model_messages


class TestToModelMessages:
    def test_empty_history(self):
        assert _to_model_messages([]) == []

    def test_user_message_becomes_model_request(self):
        result = _to_model_messages([ChatMessage(role="user", content="hi")])
        assert len(result) == 1
        assert isinstance(result[0], ModelRequest)
        assert isinstance(result[0].parts[0], UserPromptPart)
        assert result[0].parts[0].content == "hi"

    def test_assistant_message_becomes_model_response(self):
        result = _to_model_messages([ChatMessage(role="assistant", content="hello")])
        assert len(result) == 1
        assert isinstance(result[0], ModelResponse)
        assert isinstance(result[0].parts[0], TextPart)
        assert result[0].parts[0].content == "hello"

    def test_alternating_turns_preserved(self):
        history = [
            ChatMessage(role="user", content="one"),
            ChatMessage(role="assistant", content="two"),
            ChatMessage(role="user", content="three"),
        ]
        result = _to_model_messages(history)
        assert len(result) == 3
        assert isinstance(result[0], ModelRequest)
        assert isinstance(result[1], ModelResponse)
        assert isinstance(result[2], ModelRequest)

    def test_content_preserved_in_order(self):
        history = [
            ChatMessage(role="user", content="one"),
            ChatMessage(role="assistant", content="two"),
        ]
        result = _to_model_messages(history)
        assert result[0].parts[0].content == "one"
        assert result[1].parts[0].content == "two"
