from __future__ import annotations

from assistant.conversation import ConversationHistory


def test_conversation_history_stores_user_and_assistant_turns() -> None:
    history = ConversationHistory(enabled=True, max_messages=10)

    history.add_user("hello")
    history.add_assistant("hi")

    assert [(turn.role, turn.content) for turn in history.messages] == [
        ("user", "hello"),
        ("assistant", "hi"),
    ]


def test_conversation_history_enforces_max_message_limit() -> None:
    history = ConversationHistory(enabled=True, max_messages=3)

    history.add_user("one")
    history.add_assistant("two")
    history.add_user("three")
    history.add_assistant("four")

    assert [(turn.role, turn.content) for turn in history.messages] == [
        ("assistant", "two"),
        ("user", "three"),
        ("assistant", "four"),
    ]


def test_conversation_history_reset_clears_messages() -> None:
    history = ConversationHistory(enabled=True, max_messages=10)

    history.add_user("hello")
    history.reset()

    assert history.messages == []
