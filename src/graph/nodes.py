"""LangGraph node functions for text2sql workflow.

Each node is a thin wrapper around existing reasoning components.
Nodes handle state serialization and component invocation.
"""

import uuid
from typing import Dict, Any
from datetime import datetime

from .state import Text2SQLState
from ..core.session import Session
from ..utils.exceptions import AmbiguityError
from ..utils import setup_logger

logger = setup_logger(__name__)


def initialize_node(state: Text2SQLState) -> Text2SQLState:
    """Initialize session and load schema.

    This node:
    1. Creates a new Session object or loads existing one
    2. Serializes Session to state for checkpoint persistence
    3. Loads schema (already done in agent initialization)

    Args:
        state: Current workflow state

    Returns:
        Updated state with session initialized
    """
    logger.info(f"Initializing session for query: {state.user_query[:50]}...")

    # Create or load session
    if not state.session:
        # Create new session
        session = Session(
            session_id=state.session_id,
            user_query=state.user_query
        )
        logger.info(f"Created new session: {session.session_id}")
    else:
        # Restore from state
        session = Session.from_dict(state.session)
        logger.info(f"Restored existing session: {session.session_id}")

    # Store schema snapshot (will be set by agent)
    # session.schema_snapshot = schema.to_dict()  # Done by agent

    # Serialize session back to state
    state.session = session.to_dict()

    return state


def query_understanding_node(state: Text2SQLState) -> Text2SQLState:
    """Execute 3-phase query understanding.

    This node:
    1. Deserializes Session from state
    2. Calls QueryUnderstanding.analyze() (existing component)
    3. Handles AmbiguityError by setting state for graph interrupt
    4. Updates state with understanding results
    5. Serializes Session back to state

    Args:
        state: Current workflow state

    Returns:
        Updated state with understanding results or ambiguity info
    """
    logger.info("Executing query understanding (3-phase table identification)...")

    # Get components from registry
    from .components import get_components
    components = get_components(state.session_id)

    if not components:
        raise RuntimeError(
            f"Components not registered for session {state.session_id}. "
            "Agent must register components before invoking graph."
        )

    query_understanding = components["query_understanding"]

    # Deserialize session
    session = Session.from_dict(state.session)

    try:
        # Call existing QueryUnderstanding component (3-phase process)
        understanding = query_understanding.analyze(
            state.user_query,
            session
        )

        # Update state with understanding results
        state.understanding = understanding
        state.identified_tables = understanding.get("tables", [])
        state.requires_joins = understanding.get("joins_needed", False)

        # Store intermediate result in session
        session.add_intermediate_result("understanding", understanding)

        logger.info(
            f"Query understanding complete: {len(state.identified_tables)} tables identified, "
            f"joins_needed={state.requires_joins}"
        )

        # Clear any previous error
        state.error = None
        state.ambiguity_options = None

    except AmbiguityError as e:
        # Ambiguity detected - set state for graph interrupt
        logger.warning(f"Ambiguity detected: {e}")
        state.error = str(e)
        state.ambiguity_options = e.options

        # Graph will interrupt here (conditional edge routes to END)

    except Exception as e:
        # Unexpected error
        logger.error(f"Error during query understanding: {e}")
        state.error = f"Query understanding failed: {str(e)}"

    # Serialize session back to state
    state.session = session.to_dict()

    return state


def join_inference_node(state: Text2SQLState) -> Text2SQLState:
    """Infer join conditions between identified tables.

    This node:
    1. Calls JoinInference.infer_joins() for each table pair
    2. Handles join ambiguity errors
    3. Updates state with join candidates

    Args:
        state: Current workflow state

    Returns:
        Updated state with join candidates
    """
    logger.info("Inferring joins between tables...")

    # Get components from registry
    from .components import get_components
    components = get_components(state.session_id)

    if not components:
        raise RuntimeError(f"Components not registered for session {state.session_id}")

    join_inference = components["join_inference"]

    # Deserialize session
    session = Session.from_dict(state.session)

    try:
        all_joins = []

        # Pairwise join inference
        tables = state.identified_tables
        for i, table1 in enumerate(tables):
            for table2 in tables[i + 1:]:
                logger.debug(f"Inferring join: {table1} <-> {table2}")

                joins = join_inference.infer_joins(
                    table1,
                    table2,
                    constraints=state.hard_constraints,
                    session=session
                )

                if joins:
                    all_joins.extend([j.to_dict() for j in joins])

        state.join_candidates = all_joins
        session.inferred_joins = all_joins

        logger.info(f"Join inference complete: {len(all_joins)} join candidates found")

        state.error = None

    except AmbiguityError as e:
        # Join ambiguity - set state for interrupt
        logger.warning(f"Join ambiguity detected: {e}")
        state.error = str(e)
        state.ambiguity_options = e.options

    except Exception as e:
        logger.error(f"Error during join inference: {e}")
        state.error = f"Join inference failed: {str(e)}"

    # Serialize session back
    state.session = session.to_dict()

    return state


def sql_generation_node(state: Text2SQLState) -> Text2SQLState:
    """Generate or refine SQL query.

    This node:
    1. Generates SQL on first attempt
    2. Refines SQL on subsequent attempts (with error context)
    3. Increments sql_attempt_count
    4. Records attempt in state.sql_attempts

    Args:
        state: Current workflow state

    Returns:
        Updated state with generated SQL
    """
    attempt_num = state.sql_attempt_count + 1
    logger.info(f"Generating SQL (attempt {attempt_num}/{state.max_sql_attempts})...")

    # Get components from registry
    from .components import get_components
    components = get_components(state.session_id)

    if not components:
        raise RuntimeError(f"Components not registered for session {state.session_id}")

    sql_generator = components["sql_generator"]

    # Deserialize session
    session = Session.from_dict(state.session)

    try:
        if state.sql_attempt_count == 0:
            # First attempt: generate
            sql = sql_generator.generate(
                state.user_query,
                state.identified_tables,
                state.join_candidates if state.join_candidates else None,
                state.hard_constraints if state.hard_constraints else None,
                session=session
            )
        else:
            # Subsequent attempts: refine with error context
            sql = sql_generator.refine(
                state.user_query,
                state.identified_tables,
                state.last_sql,
                state.last_error,
                attempt_num,
                state.join_candidates if state.join_candidates else None,
                state.hard_constraints if state.hard_constraints else None,
                session=session
            )

        # Update state
        state.last_sql = sql
        state.sql_attempt_count += 1

        # Record attempt (success not yet determined - happens in execution node)
        logger.info(f"SQL generated successfully (attempt {attempt_num})")

        state.error = None

    except Exception as e:
        logger.error(f"Error during SQL generation: {e}")
        state.error = f"SQL generation failed: {str(e)}"
        state.last_error = str(e)

    # Serialize session back
    state.session = session.to_dict()

    return state


def sql_execution_node(state: Text2SQLState) -> Text2SQLState:
    """Validate and execute SQL query.

    This node:
    1. Validates SQL with BigQuery dry-run
    2. Executes SQL if execute_sql=True
    3. Records attempt result in state.sql_attempts
    4. Sets final_sql and query_results on success

    Args:
        state: Current workflow state

    Returns:
        Updated state with execution results
    """
    logger.info("Validating and executing SQL...")

    # Get components from registry
    from .components import get_components
    components = get_components(state.session_id)

    if not components:
        raise RuntimeError(f"Components not registered for session {state.session_id}")

    bigquery_client = components["bigquery_client"]

    # Deserialize session
    session = Session.from_dict(state.session)

    try:
        # Step 1: Validate
        validation = bigquery_client.validate_query(state.last_sql)

        if not validation["success"]:
            # Validation failed
            error_msg = validation["error"]
            logger.warning(f"SQL validation failed: {error_msg}")

            state.error = error_msg
            state.last_error = error_msg

            # Record failed attempt
            session.add_sql_attempt(
                sql=state.last_sql,
                success=False,
                error=error_msg,
                results=None
            )

        else:
            # Validation succeeded
            logger.info("SQL validation passed")

            # Step 2: Execute (if requested)
            if state.execute_sql:
                logger.info("Executing SQL query...")
                results = bigquery_client.execute_query(state.last_sql)

                if not results["success"]:
                    # Execution failed
                    error_msg = results["error"]
                    logger.warning(f"SQL execution failed: {error_msg}")

                    state.error = error_msg
                    state.last_error = error_msg

                    session.add_sql_attempt(
                        sql=state.last_sql,
                        success=False,
                        error=error_msg,
                        results=None
                    )

                else:
                    # Execution succeeded!
                    logger.info(f"SQL execution succeeded: {results.get('row_count', 0)} rows")

                    state.final_sql = state.last_sql
                    state.query_results = results
                    state.error = None

                    session.add_sql_attempt(
                        sql=state.last_sql,
                        success=True,
                        error=None,
                        results=results
                    )

            else:
                # Skip execution, just validation
                logger.info("Skipping SQL execution (execute_sql=False)")

                state.final_sql = state.last_sql
                state.error = None

                session.add_sql_attempt(
                    sql=state.last_sql,
                    success=True,
                    error=None,
                    results=None
                )

    except Exception as e:
        logger.error(f"Error during SQL execution: {e}")
        state.error = f"SQL execution failed: {str(e)}"
        state.last_error = str(e)

        session.add_sql_attempt(
            sql=state.last_sql,
            success=False,
            error=str(e),
            results=None
        )

    # Update sql_attempts in state
    state.sql_attempts = session.sql_attempts

    # Serialize session back
    state.session = session.to_dict()

    return state


def learn_from_session_node(state: Text2SQLState) -> Text2SQLState:
    """Learn from successful session.

    This node:
    1. Calls LessonLearner.learn_from_session()
    2. Extracts patterns for future queries
    3. Updates lesson repository

    Args:
        state: Current workflow state

    Returns:
        Updated state (learning happens in background)
    """
    logger.info("Learning from session...")

    # Get components from registry
    from .components import get_components
    components = get_components(state.session_id)

    if not components:
        raise RuntimeError(f"Components not registered for session {state.session_id}")

    lesson_learner = components["lesson_learner"]

    # Deserialize session
    session = Session.from_dict(state.session)

    try:
        lessons = lesson_learner.learn_from_session(session)

        if lessons:
            logger.info(f"Learned {len(lessons)} new patterns from this session")
        else:
            logger.debug("No new lessons learned from this session")

    except Exception as e:
        # Don't fail the workflow if learning fails
        logger.warning(f"Failed to learn from session: {e}")

    # No state updates needed (learning is background)
    return state


def finalize_node(state: Text2SQLState) -> Text2SQLState:
    """Finalize session and prepare final response.

    This node:
    1. Transitions session to final state (COMPLETED or FAILED)
    2. Saves session to persistence layer
    3. Prepares final response

    Args:
        state: Current workflow state

    Returns:
        Final state
    """
    logger.info("Finalizing session...")

    # Deserialize session
    session = Session.from_dict(state.session)

    # Determine final state
    if state.final_sql and not state.error:
        # Success
        from ..core.state_machine import AgentState
        session.state_machine.transition_to(
            AgentState.COMPLETED,
            reason="Successfully generated and executed SQL"
        )
        logger.info(f"Session {session.session_id} completed successfully")

    elif state.ambiguity_options:
        # Awaiting correction
        from ..core.state_machine import AgentState
        session.state_machine.transition_to(
            AgentState.AWAITING_CORRECTION,
            reason="Ambiguity requires user clarification"
        )
        logger.info(f"Session {session.session_id} awaiting user correction")

    else:
        # Failed
        from ..core.state_machine import AgentState
        session.state_machine.transition_to(
            AgentState.FAILED,
            reason=f"Error: {state.error}"
        )
        logger.warning(f"Session {session.session_id} failed")

    # Serialize session back
    state.session = session.to_dict()

    # Session will be saved by checkpointer automatically

    return state
