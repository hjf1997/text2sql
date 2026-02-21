"""Conditional routing functions for LangGraph workflow.

These functions determine which node to execute next based on the current state.
"""

from .state import Text2SQLState
from ..utils import setup_logger

logger = setup_logger(__name__)


def check_ambiguity(state: Text2SQLState) -> str:
    """Route after query understanding based on ambiguity detection.

    Args:
        state: Current workflow state

    Returns:
        "await_correction" if ambiguity detected, "continue" otherwise
    """
    if state.ambiguity_options:
        logger.info("Ambiguity detected - graph will interrupt for user correction")
        return "await_correction"

    logger.debug("No ambiguity detected - continuing workflow")
    return "continue"


def should_infer_joins(state: Text2SQLState) -> str:
    """Route after query understanding to determine if join inference is needed.

    Args:
        state: Current workflow state

    Returns:
        "join_inference" if joins needed, "sql_generation" otherwise
    """
    if state.requires_joins and len(state.identified_tables) >= 2:
        logger.info(
            f"Joins required between {len(state.identified_tables)} tables - "
            "routing to join_inference"
        )
        return "join_inference"

    logger.info("No joins required - routing directly to sql_generation")
    return "sql_generation"


def should_retry_sql(state: Text2SQLState) -> str:
    """Route after SQL generation/execution to determine retry or continue.

    This function implements the retry logic:
    - If there's an error and attempts < max: retry (route back to sql_generation)
    - If there's an error and attempts >= max: fail (route to finalize)
    - If no error: success (route to learn_lessons)

    Args:
        state: Current workflow state

    Returns:
        "sql_generation" for retry, "failed" if max attempts, "learn_lessons" on success
    """
    if state.error:
        # There's an error
        if state.sql_attempt_count < state.max_sql_attempts:
            logger.info(
                f"SQL attempt {state.sql_attempt_count} failed - "
                f"retrying (max: {state.max_sql_attempts})"
            )
            return "sql_generation"  # Retry
        else:
            logger.warning(
                f"Max SQL attempts ({state.max_sql_attempts}) reached - giving up"
            )
            return "failed"  # Give up

    # No error - success!
    logger.info("SQL execution successful - continuing to learning")
    return "learn_lessons"
