from langgraph.graph import StateGraph, END
from src.graph.state import AssistantState
from src.graph.nodes import (
    supervisor_node,
    retrieval_agent_node,
    analysis_agent_node,
    verification_agent_node,
    safety_agent_node,
    tool_execution_node,
    response_agent_node,
)


def build_graph():
    workflow = StateGraph(AssistantState)

    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("retrieval", retrieval_agent_node)
    workflow.add_node("analysis", analysis_agent_node)
    workflow.add_node("verification", verification_agent_node)
    workflow.add_node("safety", safety_agent_node)
    workflow.add_node("tool_execution", tool_execution_node)
    workflow.add_node("response", response_agent_node)

    # Define entry point
    workflow.set_entry_point("supervisor")

    # Add conditional edges from supervisor
    def route_from_supervisor(state: AssistantState) -> str:
        intent = state.get("user_intent")
        if intent == "knowledge_query":
            return "retrieval"
        elif intent == "tool_request":
            return "safety"
        return "response"

    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "retrieval": "retrieval",
            "safety": "safety",
            "response": "response",
        },
    )

    # Knowledge path
    workflow.add_edge("retrieval", "analysis")
    workflow.add_edge("analysis", "verification")
    workflow.add_edge("verification", "response")

    # Tool path: safety classifies risk, then execution is gated by the
    # `interrupt_before=["tool_execution"]` breakpoint below. The API layer
    # inspects `risk_level` after the interrupt: low risk is auto-resumed
    # immediately; anything else creates an ApprovalRequest and waits for a
    # human decision before resuming the checkpoint.
    workflow.add_edge("safety", "tool_execution")
    workflow.add_edge("tool_execution", "response")

    workflow.add_edge("response", END)

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()

    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["tool_execution"],
    )
