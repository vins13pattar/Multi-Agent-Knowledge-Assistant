import logging
from pydantic import BaseModel, Field
from typing import Literal

logger = logging.getLogger(__name__)


class RiskClassification(BaseModel):
    risk_level: Literal["low", "medium", "high", "critical"]
    rationale: str
    requires_approval: bool


def _heuristic_classify(action: str) -> RiskClassification:
    lower = action.lower()
    if "delete" in lower or "update" in lower:
        return RiskClassification(
            risk_level="high",
            rationale="Destructive or state-changing action detected (heuristic fallback).",
            requires_approval=True,
        )
    if "external" in lower or "email" in lower:
        return RiskClassification(
            risk_level="medium",
            rationale="External communication detected (heuristic fallback).",
            requires_approval=True,
        )
    return RiskClassification(
        risk_level="low",
        rationale="Safe read-only operation (heuristic fallback).",
        requires_approval=False,
    )


def classify_risk(intent: str, action: str, tool_name: str) -> RiskClassification:
    """
    Classifies the risk of an intended action to determine if HITL approval is
    required. Uses an LLM with a structured-output schema; falls back to a
    keyword heuristic if no LLM provider is configured or the call fails.
    """
    try:
        from src.providers.llm_provider import get_default_llm_provider
        from src.prompts.loader import render_prompt

        provider = get_default_llm_provider()
        prompt = render_prompt("safety", intent=intent, action=action, tool_name=tool_name)
        response = provider.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_schema=RiskClassification,
        )
        result = response.structured_output
        if isinstance(result, RiskClassification):
            return result
        return RiskClassification(**result) if isinstance(result, dict) else _heuristic_classify(action)
    except Exception as e:
        logger.warning("LLM risk classification failed, using heuristic fallback: %s", e)
        return _heuristic_classify(action)
