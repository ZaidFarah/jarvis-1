from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from agent.router import AgentRoute, AgentRouter
from agent.state import AgentState, create_agent_state


_AGENT_LOG_SINK_ID: int | None = None

try:  # pragma: no cover - optional dependency
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    END = "__end__"

    class StateGraph:  # type: ignore[override]
        def __init__(self, state_type: type[AgentState] | None = None) -> None:
            del state_type
            self._nodes: dict[str, Callable[[AgentState], AgentState]] = {}
            self._entry_point: str | None = None

        def add_node(self, name: str, func: Callable[[AgentState], AgentState]) -> None:
            self._nodes[name] = func

        def set_entry_point(self, name: str) -> None:
            self._entry_point = name

        def add_edge(self, source: str, destination: str) -> None:
            del source, destination

        def add_conditional_edges(self, source: str, condition: Callable[[AgentState], str], mapping: dict[str, str]) -> None:
            del source, condition, mapping

        def compile(self) -> "_CompiledAgentGraph":
            return _CompiledAgentGraph(self._nodes, self._entry_point)


class _CompiledAgentGraph:
    def __init__(self, nodes: dict[str, Callable[[AgentState], AgentState]], entry_point: str | None) -> None:
        self.nodes = nodes
        self.entry_point = entry_point or next(iter(nodes), "")

    def invoke(self, state: AgentState) -> AgentState:
        current = state
        route_node = self.nodes.get("route")
        dispatch_node = self.nodes.get("dispatch")
        if route_node is not None:
            current = route_node(current)
        if dispatch_node is not None:
            current = dispatch_node(current)
        return current


@dataclass(frozen=True)
class AgentRunResult:
    user_input: str
    selected_tool: str
    tool_result: str
    final_response: str
    conversation_history: str
    reason: str
    response: AssistantResponse


class AgentRuntime:
    """Experimental LangGraph-style runtime that reuses AssistantCore for execution."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        assistant: AssistantCore | None = None,
        router: AgentRouter | None = None,
    ) -> None:
        self.settings = settings or AppSettings(_env_file=None)
        self.assistant = assistant or AssistantCore(settings=self.settings)
        self.router = router or AgentRouter(self.settings)
        self.log_file = self.settings.log_dir / "agent.log"
        self.agent_logger = logger.bind(agent=True)
        self._ensure_log_sink()
        self.graph = self._build_graph()

    def run(self, user_input: str) -> AgentRunResult:
        initial_state = create_agent_state(
            user_input=user_input,
            conversation_history=self.assistant.conversation_history.format_recent_history(),
        )
        state = self.graph.invoke(initial_state)
        response = state.get("_assistant_response")
        if not isinstance(response, AssistantResponse):
            response = AssistantResponse(text=state.get("final_response", ""), accepted=False, source="local")

        return AgentRunResult(
            user_input=user_input,
            selected_tool=state.get("selected_tool", "chat"),
            tool_result=state.get("tool_result", ""),
            final_response=state.get("final_response", ""),
            conversation_history=state.get("conversation_history", ""),
            reason=state.get("_route_reason", ""),
            response=response,
        )

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("route", self._route_node)
        builder.add_node("dispatch", self._dispatch_node)
        builder.set_entry_point("route")
        builder.add_edge("route", "dispatch")
        builder.add_edge("dispatch", END)
        return builder.compile()

    def _route_node(self, state: AgentState) -> AgentState:
        route: AgentRoute = self.router.route(state.get("user_input", ""), state.get("conversation_history", ""))
        self.agent_logger.info("Agent route user_input={} tool={} reason={}", state.get("user_input", ""), route.tool_name, route.reason)
        state["selected_tool"] = route.tool_name
        state["_route_reason"] = route.reason
        return state

    def _dispatch_node(self, state: AgentState) -> AgentState:
        user_input = state.get("user_input", "")
        self.agent_logger.info("Dispatching agent tool={}", state.get("selected_tool", "chat"))
        response = self.assistant.handle_command(user_input)
        state["tool_result"] = response.text
        state["final_response"] = response.text
        state["conversation_history"] = self.assistant.conversation_history.format_recent_history()
        state["_assistant_response"] = response
        return state

    def _ensure_log_sink(self) -> None:
        global _AGENT_LOG_SINK_ID
        if _AGENT_LOG_SINK_ID is not None:
            return
        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _AGENT_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("agent")),
        )
