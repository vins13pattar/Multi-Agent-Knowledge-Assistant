import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field

from src.prompts.loader import render_prompt
from src.providers.llm_provider import get_default_llm_provider
from src.rag.store import retrieve_documents, format_citations

logger = logging.getLogger(__name__)

# Golden question set for offline RAG evaluation. `expected_source` is matched
# against the `source` filename in retrieved-chunk metadata (see
# src/rag/store.py's `format_citations` / Document loader, which sets
# `metadata["source"]` to the file path). Retrieval is run with no access
# filter (admin scope) so the eval measures retrieval quality independent of
# per-user RBAC. Keep this in sync with sample_docs/README.md's suggested
# test queries.
GOLDEN_DATASET = [
    {
        "question": "How many PTO days do I get after 4 years at the company?",
        "expected_source": "hr_policy_pto.md",
    },
    {
        "question": "What is the response time requirement for a SEV2 incident?",
        "expected_source": "engineering_incident_response_runbook.md",
    },
    {
        "question": "What file types can I upload to the knowledge base?",
        "expected_source": "product_faq.txt",
    },
    {
        "question": "What should a new employee do during their first week?",
        "expected_source": "new_hire_onboarding_guide.md",
    },
    {
        "question": "How long must accounts be deprovisioned after an employee's last day?",
        "expected_source": "security_access_control_policy.md",
    },
    {
        "question": "What was total revenue in Q3 2026?",
        "expected_source": "finance_q3_2026_report.txt",
    },
]

DATASET_NAME = "sample_docs_golden_v1"


class _Score(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


def _source_name(metadata: Dict[str, Any]) -> str:
    source = metadata.get("source", "")
    return source.rsplit("/", 1)[-1]


def _hit_rank(expected_source: str, retrieved: List) -> Optional[int]:
    """1-based rank of the first retrieved chunk from the expected document, or None."""
    for i, doc in enumerate(retrieved):
        if _source_name(doc.metadata) == expected_source:
            return i + 1
    return None


def _score_faithfulness(provider, answer: str, sources_text: str) -> float:
    try:
        prompt = render_prompt("eval_faithfulness", answer=answer, sources=sources_text)
        response = provider.generate(messages=[{"role": "user", "content": prompt}], temperature=0.0, response_schema=_Score)
        return response.structured_output.score
    except Exception as e:
        logger.warning("Faithfulness scoring failed: %s", e)
        return 0.0


def _score_relevancy(provider, question: str, answer: str) -> float:
    try:
        prompt = render_prompt("eval_relevancy", question=question, answer=answer)
        response = provider.generate(messages=[{"role": "user", "content": prompt}], temperature=0.0, response_schema=_Score)
        return response.structured_output.score
    except Exception as e:
        logger.warning("Answer relevancy scoring failed: %s", e)
        return 0.0


def run_eval(dataset: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Runs the golden question set end-to-end through retrieval + analysis,
    scoring retrieval (hit rate, MRR) and generation (faithfulness, answer
    relevancy via LLM-judge). Returns a summary dict plus per-question results;
    does not touch the database — callers persist as they see fit.
    """
    dataset = dataset if dataset is not None else GOLDEN_DATASET
    provider = get_default_llm_provider()

    results = []
    for item in dataset:
        question = item["question"]
        expected_source = item.get("expected_source")

        retrieved = retrieve_documents(question, k=4, filter_metadata=None)
        rank = _hit_rank(expected_source, retrieved) if expected_source else None
        hit = rank is not None
        reciprocal_rank = (1.0 / rank) if rank else 0.0

        sources_text = "\n\n".join(f"[Source {i+1}] {d.page_content}" for i, d in enumerate(retrieved))
        answer = ""
        faithfulness = None
        relevancy = None
        if retrieved:
            try:
                prompt = render_prompt("analysis", question=question, sources=sources_text)
                answer = provider.generate(messages=[{"role": "user", "content": prompt}], temperature=0.2).content.strip()
            except Exception as e:
                logger.warning("Answer generation failed for eval question %r: %s", question, e)
            if answer:
                faithfulness = _score_faithfulness(provider, answer, sources_text)
                relevancy = _score_relevancy(provider, question, answer)

        results.append({
            "question": question,
            "expected_source": expected_source,
            "retrieved_sources": [_source_name(d.metadata) for d in retrieved],
            "hit": hit,
            "reciprocal_rank": reciprocal_rank,
            "faithfulness_score": faithfulness,
            "answer_relevancy_score": relevancy,
            "generated_answer": answer,
        })

    def _avg(key):
        vals = [r[key] for r in results if r[key] is not None]
        return (sum(vals) / len(vals)) if vals else None

    summary = {
        "question_count": len(results),
        "avg_hit_rate": _avg("hit"),
        "avg_mrr": _avg("reciprocal_rank"),
        "avg_faithfulness": _avg("faithfulness_score"),
        "avg_answer_relevancy": _avg("answer_relevancy_score"),
    }
    return {"summary": summary, "results": results}
