import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session

from src.database.models import RagEvalRun, RagEvalRunResult, RagEvalRunStatus
from src.database.session import db_session
from src.rag.eval import run_eval, DATASET_NAME

logger = logging.getLogger(__name__)


def create_run_row(db: Session, triggered_by: Optional[str]) -> str:
    """Creates the RagEvalRun row synchronously (fast, no LLM calls) so a
    caller — e.g. the trigger endpoint — can hand back a run id immediately
    and let the actual eval execute in the background.
    """
    run = RagEvalRun(
        triggered_by=triggered_by,
        dataset_name=DATASET_NAME,
        status=RagEvalRunStatus.running,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return str(run.id)


def execute_eval_run(run_id: str) -> None:
    """Runs the golden-dataset RAG eval and fills in the RagEvalRun (created
    via create_run_row) plus its per-question RagEvalRunResult rows. Opens its
    own DB session so it's safe to call from a FastAPI BackgroundTask (the
    request-scoped session is closed by the time background tasks run) or a
    standalone script.
    """
    with db_session() as db:
        run = db.query(RagEvalRun).filter(RagEvalRun.id == run_id).first()
        if run is None:
            logger.error("RagEvalRun %s not found", run_id)
            return
        try:
            outcome = run_eval()
            summary = outcome["summary"]

            for r in outcome["results"]:
                db.add(RagEvalRunResult(
                    run_id=run.id,
                    question=r["question"],
                    expected_source=r["expected_source"],
                    retrieved_sources=r["retrieved_sources"],
                    hit=r["hit"],
                    reciprocal_rank=r["reciprocal_rank"],
                    faithfulness_score=r["faithfulness_score"],
                    answer_relevancy_score=r["answer_relevancy_score"],
                    generated_answer=r["generated_answer"],
                ))

            run.status = RagEvalRunStatus.completed
            run.question_count = summary["question_count"]
            run.avg_hit_rate = summary["avg_hit_rate"]
            run.avg_mrr = summary["avg_mrr"]
            run.avg_faithfulness = summary["avg_faithfulness"]
            run.avg_answer_relevancy = summary["avg_answer_relevancy"]
            run.finished_at = datetime.utcnow()
        except Exception as e:
            logger.exception("RAG eval run %s failed", run_id)
            run.status = RagEvalRunStatus.failed
            run.error = str(e)
            run.finished_at = datetime.utcnow()
        # db_session() commits on clean exit and rolls back on exception; an
        # exception here has already been caught and turned into a "failed"
        # row, so let this fall through to a normal commit.
