"""
Offline RAG evaluation CLI — runs the golden question set (src/rag/eval.py)
and persists a RagEvalRun + RagEvalRunResult rows, same as triggering it from
the admin dashboard's "Run Eval" button.

Run inside the API container: python scripts/run_rag_eval.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.session import db_session
from apps.api.eval_runner import create_run_row, execute_eval_run


def main():
    with db_session() as db:
        run_id = create_run_row(db, triggered_by=None)
    execute_eval_run(run_id)
    print(f"RAG eval run {run_id} complete.")


if __name__ == "__main__":
    main()
