import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.graph.state import AssistantState
from src.prompts.loader import render_prompt
from src.providers.llm_provider import get_default_llm_provider

logger = logging.getLogger(__name__)


def _conversation_text(state: AssistantState, max_turns: int = 10) -> str:
    messages = state.get("messages", [])[-max_turns:]
    return "\n".join(f'{m.get("role", "user")}: {m.get("content", "")}' for m in messages)


def _last_user_message(state: AssistantState) -> str:
    messages = state.get("messages", [])
    return messages[-1].get("content", "") if messages else ""


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

class IntentClassification(BaseModel):
    intent: Literal["knowledge_query", "tool_request", "general_conversation"]
    rationale: str


class ToolCallExtraction(BaseModel):
    tool_name: str = Field(description="Must exactly match one of the available tool names.")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    action_description: str


def supervisor_node(state: AssistantState) -> Dict[str, Any]:
    """Uses an LLM to classify the user's intent and, for tool requests, extract the tool call."""
    messages = state.get("messages", [])
    if not messages:
        return {"user_intent": "general_conversation"}

    provider = get_default_llm_provider()
    conversation = _conversation_text(state)

    try:
        prompt = render_prompt("supervisor", conversation=conversation)
        response = provider.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_schema=IntentClassification,
        )
        classification: IntentClassification = response.structured_output
        intent = classification.intent
    except Exception as e:
        logger.warning("Supervisor LLM classification failed, defaulting to general_conversation: %s", e)
        intent = "general_conversation"

    if intent != "tool_request":
        return {"user_intent": intent}

    from src.tools.registry import get_tool_registry
    registry = get_tool_registry()
    tools_desc = "\n".join(f"- {t.name}: {t.description}" for t in registry.list_tools())

    try:
        extraction_prompt = (
            "Available tools:\n" + tools_desc +
            f"\n\nUser request: {_last_user_message(state)}\n\n"
            "Extract the tool call that best satisfies this request."
        )
        response = provider.generate(
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0.0,
            response_schema=ToolCallExtraction,
        )
        extraction: ToolCallExtraction = response.structured_output
        tool_request = {
            "tool_name": extraction.tool_name,
            "arguments": extraction.arguments,
            "action_description": extraction.action_description,
        }
    except Exception as e:
        logger.warning("Tool call extraction failed: %s", e)
        tool_request = {
            "tool_name": "unknown",
            "arguments": {},
            "action_description": _last_user_message(state),
        }

    return {"user_intent": "tool_request", "tool_requests": [tool_request]}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieval_agent_node(state: AssistantState) -> Dict[str, Any]:
    """Rewrites the query via LLM, then retrieves relevant documents."""
    from src.rag.retrieval.chroma_store import retrieve_documents, access_scope_filter

    messages = state.get("messages", [])
    if not messages:
        return {}

    raw_query = _last_user_message(state)
    query = raw_query
    try:
        provider = get_default_llm_provider()
        prompt = render_prompt("retrieval", conversation=_conversation_text(state))
        response = provider.generate(messages=[{"role": "user", "content": prompt}], temperature=0.0)
        rewritten = response.content.strip()
        if rewritten:
            query = rewritten
    except Exception as e:
        logger.warning("Query rewrite failed, using raw message: %s", e)

    results = retrieve_documents(query, filter_metadata=access_scope_filter(state.get("user_role", "employee")))
    docs_formatted = [{"content": d.page_content, "metadata": d.metadata} for d in results]
    return {"retrieved_documents": docs_formatted}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analysis_agent_node(state: AssistantState) -> Dict[str, Any]:
    """Synthesizes a draft answer from retrieved documents via LLM."""
    retrieved = state.get("retrieved_documents", [])
    if not retrieved:
        return {"response_draft": "No relevant documents were found in the knowledge base for this question."}

    sources_text = "\n\n".join(
        f"[Source {i+1}] {d['content']}" for i, d in enumerate(retrieved)
    )
    question = _last_user_message(state)

    try:
        provider = get_default_llm_provider()
        prompt = render_prompt("analysis", question=question, sources=sources_text)
        response = provider.generate(messages=[{"role": "user", "content": prompt}], temperature=0.2)
        draft = response.content.strip()
    except Exception as e:
        logger.warning("Analysis LLM call failed: %s", e)
        draft = "Based on the retrieved documents, here is what I found: " + sources_text[:500]

    return {"response_draft": draft}


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class VerificationResult(BaseModel):
    status: Literal["verified", "unsupported_claims"]
    unsupported_claims: List[str] = Field(default_factory=list)


def verification_agent_node(state: AssistantState) -> Dict[str, Any]:
    """Checks the draft against retrieved sources for unsupported claims via LLM."""
    draft = state.get("response_draft", "")
    retrieved = state.get("retrieved_documents", [])
    if not draft or not retrieved:
        return {"verification_result": {"status": "verified", "unsupported_claims": []}}

    sources_text = "\n\n".join(f"[Source {i+1}] {d['content']}" for i, d in enumerate(retrieved))

    try:
        provider = get_default_llm_provider()
        prompt = render_prompt("verification", draft=draft, sources=sources_text)
        response = provider.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_schema=VerificationResult,
        )
        result: VerificationResult = response.structured_output
        return {"verification_result": result.model_dump()}
    except Exception as e:
        logger.warning("Verification LLM call failed, assuming verified: %s", e)
        return {"verification_result": {"status": "verified", "unsupported_claims": []}}


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def safety_agent_node(state: AssistantState) -> Dict[str, Any]:
    """Evaluates the risk of the requested tool action via the (LLM-backed) risk classifier."""
    from src.hitl.safety_classifier import classify_risk

    tool_requests = state.get("tool_requests", [])
    if not tool_requests:
        return {"risk_level": "low"}

    request = tool_requests[-1]
    classification = classify_risk(
        intent=state.get("user_intent", "tool_request"),
        action=request.get("action_description", ""),
        tool_name=request.get("tool_name", ""),
    )
    return {"risk_level": classification.risk_level}


# ---------------------------------------------------------------------------
# Tool execution (HITL-gated)
# ---------------------------------------------------------------------------

def tool_execution_node(state: AssistantState) -> Dict[str, Any]:
    """
    Executes queued tool requests. This node is preceded by an interrupt in the
    compiled graph — by the time it runs, the caller has either auto-approved
    (low risk) or the human has approved/rejected via /api/v1/approvals, which
    updates `approval_status` on the checkpoint before resuming.
    """
    # Fail closed: an unclassified action is never treated as low risk.
    risk = state.get("risk_level") or "critical"
    approval_status = state.get("approval_status")

    if risk != "low" and approval_status != "approved":
        if approval_status == "rejected":
            return {"tool_results": [{"status": "rejected", "message": "This action was rejected by an approver."}]}
        return {"tool_results": [{"status": "pending_approval", "message": "Awaiting approver decision."}]}

    from src.tools.registry import get_tool_registry
    registry = get_tool_registry()

    results = []
    for request in state.get("tool_requests", []):
        tool_name = request.get("tool_name")
        arguments = dict(request.get("arguments", {}))
        if tool_name == "search_knowledge_base":
            arguments["user_role"] = state.get("user_role", "employee")
        try:
            output = registry.execute(tool_name, **arguments)
            results.append({"tool_name": tool_name, "status": "success", "output": output})
        except Exception as e:
            logger.warning("Tool execution failed for %s: %s", tool_name, e)
            results.append({"tool_name": tool_name, "status": "failed", "error": str(e)})

    return {"tool_results": results}


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

def response_agent_node(state: AssistantState) -> Dict[str, Any]:
    """Formats the final response: polishes a knowledge-query draft, summarizes a
    tool outcome, or answers conversationally — including citations when available."""
    provider = get_default_llm_provider()
    draft = state.get("response_draft")
    tool_results = state.get("tool_results", [])
    retrieved = state.get("retrieved_documents", [])

    citations: List[str] = []
    if retrieved:
        from src.rag.citations.formatter import format_citations
        from langchain_core.documents import Document
        docs = [Document(page_content=d["content"], metadata=d["metadata"]) for d in retrieved]
        citations.append(format_citations(docs))

    if draft:
        verification = state.get("verification_result") or {}
        note = ""
        if verification.get("status") == "unsupported_claims":
            note = "Note: some claims in the draft could not be fully verified against the sources — soften or flag them appropriately."
        try:
            prompt = render_prompt("response", draft=draft, verification_note=note)
            response = provider.generate(messages=[{"role": "user", "content": prompt}], temperature=0.3)
            final_text = response.content.strip()
        except Exception as e:
            logger.warning("Response polishing failed, using draft as-is: %s", e)
            final_text = draft
        return {"messages": [{"role": "assistant", "content": final_text}], "citations": citations}

    if tool_results:
        result = tool_results[-1]
        status = result.get("status")
        if status == "success":
            text = f"Done — {result.get('tool_name')} completed successfully. Result: {result.get('output')}"
        elif status == "pending_approval":
            text = "This action requires admin approval before it can proceed. You'll be notified once it's reviewed."
        elif status == "rejected":
            text = "This action was reviewed and rejected by an approver, so it was not carried out."
        else:
            text = f"The action could not be completed: {result.get('error', 'unknown error')}"
        return {"messages": [{"role": "assistant", "content": text}], "citations": citations}

    # General conversation — answer directly.
    try:
        conversation = _conversation_text(state)
        response = provider.generate(
            messages=[{"role": "user", "content": f"Continue this conversation naturally and helpfully:\n{conversation}"}],
            temperature=0.5,
        )
        text = response.content.strip()
    except Exception as e:
        logger.warning("General conversation LLM call failed: %s", e)
        text = "I'm not able to answer that right now — please try again shortly."

    return {"messages": [{"role": "assistant", "content": text}], "citations": citations}
