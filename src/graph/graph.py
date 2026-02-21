"""LangGraph workflow definition for text2sql.

This module defines and compiles the complete workflow graph,
connecting all nodes with conditional routing logic.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from .state import Text2SQLState
from .nodes import (
    initialize_node,
    query_understanding_node,
    join_inference_node,
    sql_generation_node,
    sql_execution_node,
    learn_from_session_node,
    finalize_node,
)
from .edges import (
    should_retry_sql,
)
from ..utils import setup_logger

logger = setup_logger(__name__)


def create_workflow() -> StateGraph:
    """Create and configure the LangGraph workflow.

    Returns:
        Configured StateGraph (not yet compiled)
    """
    logger.info("Creating LangGraph workflow...")

    # Create the graph
    workflow = StateGraph(Text2SQLState)

    # ==== Add all nodes ====
    workflow.add_node("initialize", initialize_node)
    workflow.add_node("query_understanding", query_understanding_node)
    workflow.add_node("join_inference", join_inference_node)
    workflow.add_node("sql_generation", sql_generation_node)
    workflow.add_node("sql_execution", sql_execution_node)
    workflow.add_node("learn_lessons", learn_from_session_node)
    workflow.add_node("finalize", finalize_node)

    # ==== Set entry point ====
    workflow.set_entry_point("initialize")

    # ==== Define the flow ====

    # Initialize → Query Understanding
    workflow.add_edge("initialize", "query_understanding")

    # Query Understanding → Combined routing (ambiguity check + join check)
    def route_after_query_understanding(state: Text2SQLState) -> str:
        """Combined routing after query understanding.

        Handles both ambiguity detection and join inference routing.
        """
        # First check ambiguity
        if state.ambiguity_options:
            return "await_correction"

        # Then check if joins needed
        if state.requires_joins and len(state.identified_tables) >= 2:
            return "join_inference"

        # Otherwise go directly to SQL generation
        return "sql_generation"

    workflow.add_conditional_edges(
        "query_understanding",
        route_after_query_understanding,
        {
            "await_correction": END,
            "join_inference": "join_inference",
            "sql_generation": "sql_generation",
        }
    )

    # Join Inference → SQL Generation
    # (After join inference, always go to SQL generation)
    # But wait, join inference can also raise ambiguity!

    def route_after_join_inference(state: Text2SQLState) -> str:
        """Route after join inference."""
        if state.ambiguity_options:
            return "await_correction"
        return "sql_generation"

    workflow.add_conditional_edges(
        "join_inference",
        route_after_join_inference,
        {
            "await_correction": END,
            "sql_generation": "sql_generation",
        }
    )

    # SQL Generation → SQL Execution
    # (Always go to execution after generation)
    workflow.add_edge("sql_generation", "sql_execution")

    # SQL Execution → Retry or Continue
    workflow.add_conditional_edges(
        "sql_execution",
        should_retry_sql,
        {
            "sql_generation": "sql_generation",  # Retry
            "failed": "finalize",  # Give up
            "learn_lessons": "learn_lessons",  # Success
        }
    )

    # Learn Lessons → Finalize
    workflow.add_edge("learn_lessons", "finalize")

    # Finalize → END
    workflow.add_edge("finalize", END)

    logger.info("Workflow graph created successfully")

    return workflow


def compile_app(checkpointer_path: str = "text2sql_checkpoints.db"):
    """Compile the workflow graph with checkpointer.

    Args:
        checkpointer_path: Path to SQLite checkpoint database

    Returns:
        Compiled LangGraph application
    """
    logger.info(f"Compiling workflow with checkpointer: {checkpointer_path}")

    # Create workflow
    workflow = create_workflow()

    # Create checkpointer
    # Note: SqliteSaver.from_conn_string() returns a context manager in newer versions
    # We use __enter__ to get the actual saver instance
    checkpointer_cm = SqliteSaver.from_conn_string(checkpointer_path)
    checkpointer = checkpointer_cm.__enter__()

    # Compile
    app = workflow.compile(checkpointer=checkpointer)

    logger.info("Workflow compiled successfully")

    return app


# Create the default compiled app
# This will be imported by the agent
app = compile_app()
