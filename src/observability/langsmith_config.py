import os
import logging
from langsmith import Client

logger = logging.getLogger(__name__)

def setup_langsmith():
    """
    Initializes LangSmith tracing if configured.
    Langchain/LangGraph automatically picks up the LANGCHAIN_TRACING_V2 env var,
    so this mostly serves as a programmatic check/setup for evaluations.
    """
    if os.getenv("LANGCHAIN_TRACING_V2") == "true":
        logger.info("LangSmith tracing is ENABLED.")
        try:
            client = Client()
            return client
        except Exception as e:
            logger.error(f"Failed to initialize LangSmith client: {e}")
            return None
    else:
        logger.info("LangSmith tracing is disabled (LANGCHAIN_TRACING_V2 != 'true').")
        return None

def run_evaluation(dataset_name: str, evaluator_funcs: list):
    """
    Runs a test dataset against the configured agent workflow.
    Requires LangSmith setup.
    """
    client = setup_langsmith()
    if not client:
        raise ValueError("LangSmith is not configured. Cannot run evaluations.")
        
    logger.info(f"Running evaluation against dataset: {dataset_name}")
    # In a real setup, we would use evaluate() from langsmith
    # e.g., evaluate(target_app, data=dataset_name, evaluators=evaluator_funcs)
    pass
