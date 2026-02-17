"""Main agent orchestrator for automated text-to-SQL conversion."""

from typing import Optional, Dict, Any, List
from ..schema import Schema, schema_loader
from ..core import Session, session_manager, AgentState
from ..database import bigquery_client
from ..reasoning import QueryUnderstanding, JoinInference, SQLGenerator
from ..correction import CorrectionParser, Correction
from ..memory import LessonLearner
from ..config import settings
from ..utils import (
    setup_logger,
    AmbiguityError,
    MaxIterationsError,
    ValidationError,
)

logger = setup_logger(__name__)


class Text2SQLAgent:
    """Automated text-to-SQL agent that handles the complete workflow.

    This agent automatically:
    1. Loads schema from directory
    2. Understands user queries via LLM
    3. Identifies required tables and columns
    4. Infers joins between tables
    5. Generates SQL queries
    6. Executes on BigQuery
    7. Handles corrections and iterations
    """

    def __init__(
        self,
        schema_dir: Optional[str] = None,
        schema: Optional[Schema] = None,
        max_iterations: Optional[int] = None,
        max_correction_attempts: Optional[int] = None,
    ):
        """Initialize the text-to-SQL agent.

        Args:
            schema_dir: Directory containing schema Excel files
            schema: Pre-loaded schema (if None, loads from schema_dir)
            max_iterations: Maximum reasoning iterations
            max_correction_attempts: Maximum correction attempts
        """
        # Load schema
        if schema:
            self.schema = schema
        else:
            logger.info("Loading schema...")
            self.schema = schema_loader.load_from_excel(schema_dir=schema_dir)
            logger.info(f"✓ Loaded {len(self.schema.tables)} tables")

        # Initialize reasoning components
        self.query_understanding = QueryUnderstanding(self.schema)
        self.join_inference = JoinInference(
            self.schema,
            confidence_threshold=settings.get("agent.confidence_threshold", 0.75)
        )
        self.sql_generator = SQLGenerator(self.schema)

        # Initialize memory/learning component
        self.lesson_learner = LessonLearner()

        # Configuration
        self.max_iterations = max_iterations or settings.get("agent.max_iterations", 5)
        self.max_correction_attempts = max_correction_attempts or settings.get(
            "agent.max_correction_attempts", 3
        )

        logger.info("✓ Text2SQL Agent initialized")

    def query(
        self,
        user_query: str,
        execute: bool = True,
        return_session: bool = False,
    ) -> Dict[str, Any]:
        """Process a natural language query and return results.

        Args:
            user_query: Natural language query
            execute: Whether to execute the SQL (if False, only generates SQL)
            return_session: Whether to return the session object

        Returns:
            Dictionary containing:
                - sql: Generated SQL query
                - results: Query results (if execute=True)
                - session: Session object (if return_session=True)
                - success: Boolean indicating success
                - error: Error message (if failed)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing query: {user_query}")
        logger.info(f"{'='*60}")

        # Create session
        session = session_manager.create_session(user_query)
        session.schema_snapshot = self.schema.to_dict()
        session.add_message("user", user_query)

        try:
            # Run the agent workflow
            sql, results = self._run_workflow(session, user_query, execute)

            # Mark as completed
            session.state_machine.transition_to(
                AgentState.COMPLETED,
                reason="Successfully generated and executed SQL"
            )
            session_manager.save_session(session)

            # Learn from this successful session
            try:
                lessons_learned = self.lesson_learner.learn_from_session(session)
                if lessons_learned:
                    logger.info(f"Learned {len(lessons_learned)} new patterns from this query")
            except Exception as e:
                logger.warning(f"Failed to learn from session: {e}")

            response = {
                "success": True,
                "sql": sql,
            }

            if execute and results:
                response["results"] = results
                response["row_count"] = results.get("row_count", 0)

            if return_session:
                response["session"] = session

            logger.info(f"✓ Query completed successfully")
            return response

        except AmbiguityError as e:
            logger.warning(f"Ambiguity detected: {e}")
            session.state_machine.transition_to(
                AgentState.AWAITING_CORRECTION,
                reason="Ambiguity requires user clarification"
            )
            session_manager.save_session(session)

            return {
                "success": False,
                "error": "ambiguity",
                "message": str(e),
                "options": e.options,
                "session_id": session.session_id,
                "session": session if return_session else None,
            }

        except MaxIterationsError as e:
            logger.error(f"Max iterations reached: {e}")
            session.state_machine.transition_to(
                AgentState.FAILED,
                reason="Maximum iterations reached"
            )
            self._generate_failure_summary(session, str(e))
            session_manager.save_session(session)

            return {
                "success": False,
                "error": "max_iterations",
                "message": str(e),
                "failure_summary": session.failure_summary,
                "session_id": session.session_id,
                "session": session if return_session else None,
            }

        except Exception as e:
            logger.error(f"Query processing failed: {str(e)}")
            session.state_machine.transition_to(
                AgentState.FAILED,
                reason=f"Error: {str(e)}"
            )
            self._generate_failure_summary(session, str(e))
            session_manager.save_session(session)

            return {
                "success": False,
                "error": "processing_failed",
                "message": str(e),
                "failure_summary": session.failure_summary,
                "session_id": session.session_id,
                "session": session if return_session else None,
            }

    def query_with_correction(
        self,
        session_id: str,
        correction: str,
        execute: bool = True,
    ) -> Dict[str, Any]:
        """Restart query processing with user correction.

        Args:
            session_id: Session ID to resume
            correction: User correction (natural language or structured)
            execute: Whether to execute the SQL

        Returns:
            Result dictionary (same format as query())
        """
        logger.info(f"Resuming session {session_id} with correction")

        # Load session
        session = session_manager.load_session(session_id)

        # Check correction attempts
        if session.correction_attempt >= self.max_correction_attempts:
            return {
                "success": False,
                "error": "max_corrections",
                "message": f"Maximum correction attempts ({self.max_correction_attempts}) reached",
                "session_id": session_id,
            }

        # Parse and apply correction
        try:
            parsed_correction = CorrectionParser.parse(correction)
            session.add_correction(parsed_correction)
            session.increment_correction_attempt()

            logger.info(f"Applied correction: {parsed_correction.to_constraint_string()}")

        except Exception as e:
            logger.error(f"Failed to parse correction: {e}")
            return {
                "success": False,
                "error": "invalid_correction",
                "message": f"Could not parse correction: {str(e)}",
                "session_id": session_id,
            }

        # Reset state and restart workflow
        session.state_machine.transition_to(
            AgentState.QUERY_UNDERSTANDING,
            reason="Restarting with user correction"
        )
        session.iteration_count = 0

        # Re-run workflow with corrections
        try:
            sql, results = self._run_workflow(
                session,
                session.original_query,
                execute
            )

            session.state_machine.transition_to(AgentState.COMPLETED)
            session_manager.save_session(session)

            response = {
                "success": True,
                "sql": sql,
                "session_id": session_id,
            }

            if execute and results:
                response["results"] = results

            return response

        except Exception as e:
            logger.error(f"Query failed after correction: {e}")
            session.state_machine.transition_to(AgentState.FAILED)
            self._generate_failure_summary(session, str(e))
            session_manager.save_session(session)

            return {
                "success": False,
                "error": "processing_failed",
                "message": str(e),
                "failure_summary": session.failure_summary,
                "session_id": session_id,
            }

    def _run_workflow(
        self,
        session: Session,
        user_query: str,
        execute: bool,
    ) -> tuple[str, Optional[Dict]]:
        """Run the main agent workflow.

        Args:
            session: Session object
            user_query: User query
            execute: Whether to execute SQL

        Returns:
            Tuple of (sql, results)

        Raises:
            Various exceptions on failure
        """
        # Step 1: Query Understanding
        logger.info("Step 1: Understanding query...")
        session.state_machine.transition_to(
            AgentState.QUERY_UNDERSTANDING,
            reason="Analyzing user query"
        )

        understanding = self.query_understanding.analyze(user_query, session)
        session.identified_tables = understanding["tables"]
        session.add_intermediate_result("understanding", understanding)

        logger.info(f"  ✓ Identified tables: {understanding['tables']}")
        logger.info(f"  ✓ Joins needed: {understanding['joins_needed']}")

        # Step 2: Join Inference (if needed)
        join_candidates = []
        if understanding["joins_needed"] and len(understanding["tables"]) >= 2:
            logger.info("Step 2: Inferring table joins...")
            session.state_machine.transition_to(
                AgentState.JOIN_INFERENCE,
                reason="Determining table relationships"
            )

            try:
                # Infer joins between all pairs of tables
                for i, table1 in enumerate(understanding["tables"]):
                    for table2 in understanding["tables"][i+1:]:
                        joins = self.join_inference.infer_joins(
                            table1,
                            table2,
                            constraints=session.hard_constraints,
                            session=session,
                        )
                        if joins:
                            join_candidates.extend(joins)
                            logger.info(f"  ✓ Found join: {joins[0]}")

                session.inferred_joins = [j.to_dict() for j in join_candidates]

            except AmbiguityError:
                # Re-raise to caller for user resolution
                raise

        # Step 3: SQL Generation with Retry Loop
        logger.info("Step 3: Generating SQL with automatic retry...")
        session.state_machine.transition_to(
            AgentState.GENERATING_SQL,
            reason="Creating SQL query"
        )
        session.increment_iteration()

        # Get max SQL attempts from config
        max_sql_attempts = settings.get("agent.max_sql_attempts", 3)

        sql = None
        results = None
        last_error = None

        # Retry loop for SQL generation and execution
        for attempt in range(1, max_sql_attempts + 1):
            try:
                logger.info(f"  SQL Attempt {attempt}/{max_sql_attempts}")

                # Generate SQL (first attempt) or refine SQL (subsequent attempts)
                if attempt == 1:
                    sql = self.sql_generator.generate(
                        user_query,
                        understanding["tables"],
                        join_candidates if join_candidates else None,
                        session.hard_constraints if session.hard_constraints else None,
                        session=session,
                    )
                else:
                    # Refine based on previous error
                    sql = self.sql_generator.refine(
                        user_query,
                        understanding["tables"],
                        sql,  # Previous SQL
                        last_error,  # Error message
                        attempt,
                        join_candidates if join_candidates else None,
                        session.hard_constraints if session.hard_constraints else None,
                        session=session,
                    )

                logger.info(f"    ✓ SQL generated (attempt {attempt})")

                # Execute if requested
                if execute:
                    logger.info(f"    Validating SQL (attempt {attempt})...")
                    session.state_machine.transition_to(
                        AgentState.EXECUTING_QUERY,
                        reason=f"Running query (attempt {attempt})"
                    )

                    # Validate first
                    validation = bigquery_client.validate_query(sql)
                    if not validation["success"]:
                        error_msg = validation.get("error", "Unknown validation error")
                        logger.warning(f"    ✗ Validation failed: {error_msg}")
                        session.add_sql_attempt(sql, success=False, error=f"Validation: {error_msg}")
                        last_error = error_msg

                        if attempt < max_sql_attempts:
                            logger.info(f"    Retrying with error feedback...")
                            continue
                        else:
                            raise ValidationError(f"SQL validation failed after {max_sql_attempts} attempts: {error_msg}")

                    # Execute
                    logger.info(f"    Executing query (attempt {attempt})...")
                    results = bigquery_client.execute_query(sql)

                    if not results["success"]:
                        error_msg = results.get("error", "Unknown execution error")
                        logger.warning(f"    ✗ Execution failed: {error_msg}")
                        session.add_sql_attempt(sql, success=False, error=f"Execution: {error_msg}")
                        last_error = error_msg

                        if attempt < max_sql_attempts:
                            logger.info(f"    Retrying with error feedback...")
                            continue
                        else:
                            raise ValidationError(f"Query execution failed after {max_sql_attempts} attempts: {error_msg}")

                    # Success!
                    session.add_sql_attempt(sql, success=True, results=results)
                    logger.info(f"  ✓ Query executed successfully (attempt {attempt}): {results['row_count']} rows returned")
                    break

                else:
                    # Not executing, just return generated SQL
                    session.add_sql_attempt(sql, success=True)
                    logger.info(f"  ✓ SQL generated successfully (attempt {attempt})")
                    break

            except Exception as e:
                # Unexpected error during generation
                error_msg = str(e)
                logger.error(f"    ✗ Unexpected error in attempt {attempt}: {error_msg}")
                session.add_sql_attempt(sql if sql else "GENERATION_FAILED", success=False, error=error_msg)

                if attempt < max_sql_attempts:
                    last_error = error_msg
                    logger.info(f"    Retrying after unexpected error...")
                    continue
                else:
                    raise

        return sql, results

    def _generate_failure_summary(self, session: Session, error: str):
        """Generate failure summary for session.

        Args:
            session: Session object
            error: Error message
        """
        summary = {
            "user_query": session.original_query,
            "identified_tables": session.identified_tables,
            "attempted_iterations": session.iteration_count,
            "correction_attempts": session.correction_attempt,
            "error": error,
            "sql_attempts": len(session.sql_attempts),
            "recommendations": self._generate_recommendations(session, error),
        }

        session.set_failure_summary(summary)
        logger.info("Generated failure summary")

    def _generate_recommendations(self, session: Session, error: str) -> List[str]:
        """Generate recommendations for resolving failure.

        Args:
            session: Session object
            error: Error message

        Returns:
            List of recommendations
        """
        recommendations = []

        if "ambiguity" in error.lower():
            recommendations.append("Provide clarification on the ambiguous tables or joins")

        if not session.identified_tables:
            recommendations.append("Try rephrasing the query with more specific table or entity names")

        if session.correction_attempt >= self.max_correction_attempts:
            recommendations.append("Consider writing the SQL query manually")

        if "validation" in error.lower():
            recommendations.append("Check SQL syntax and table/column names")

        return recommendations
