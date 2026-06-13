from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    conversation_history: str
    selected_tool: str
    tool_result: str
    final_response: str


def create_agent_state(user_input: str, conversation_history: str = "") -> AgentState:
    return {
        "user_input": user_input,
        "conversation_history": conversation_history,
        "selected_tool": "chat",
        "tool_result": "",
        "final_response": "",
    }
