"""Assemble the LangGraph state machine from an engine + executor.

This is the one place LangGraph is imported. Every node is wrapped by :func:`traced` so a run
becomes a span tree when tracing is enabled.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from aql.adapters.llm.base import LLMEngine
from aql.adapters.tools.executor import ToolExecutor
from aql.domain.state import AgentState
from aql.graph.nodes import Nodes
from aql.graph.routing import route_after_plan, route_after_validate, route_after_validate_plan
from aql.graph.tracing import traced

__all__ = ["build_graph"]


def build_graph(engine: LLMEngine, executor: ToolExecutor) -> Any:
    """Return the compiled agent graph (a ``CompiledStateGraph`` over :class:`AgentState`)."""
    nodes = Nodes(engine, executor)
    graph = StateGraph(AgentState)

    graph.add_node("plan", traced("plan", nodes.plan))
    graph.add_node("act", traced("act", nodes.act))
    graph.add_node("validate", traced("validate", nodes.validate))
    graph.add_node("synthesize", traced("synthesize", nodes.synthesize))
    graph.add_node("validate_plan", traced("validate_plan", nodes.validate_plan))
    graph.add_node("refuse", traced("refuse", nodes.refuse))
    graph.add_node("finalize", traced("finalize", nodes.finalize))

    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan", route_after_plan, {"act": "act", "refuse": "refuse", "synthesize": "synthesize"}
    )
    graph.add_edge("act", "validate")
    graph.add_conditional_edges(
        "validate", route_after_validate, {"act": "act", "synthesize": "synthesize"}
    )
    graph.add_edge("synthesize", "validate_plan")
    graph.add_conditional_edges(
        "validate_plan",
        route_after_validate_plan,
        {"finalize": "finalize", "synthesize": "synthesize", "refuse": "refuse"},
    )
    graph.add_edge("refuse", END)
    graph.add_edge("finalize", END)

    return graph.compile()
