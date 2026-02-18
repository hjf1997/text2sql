"""Automatic lesson extraction from query sessions."""

import re
import uuid
from typing import List, Optional, Dict
from ..core import Session, AgentState
from .models import (
    TableMappingLesson,
    ColumnMappingLesson,
    ErrorPatternLesson,
)
from .repository import lesson_repository
from ..utils import setup_logger

logger = setup_logger(__name__)


class LessonLearner:
    """Automatically extract lessons from completed sessions."""

    def __init__(self, repository=None):
        """Initialize lesson learner.

        Args:
            repository: Lesson repository (uses global instance if None)
        """
        self.repository = repository or lesson_repository

    def learn_from_session(self, session: Session) -> List:
        """Extract lessons from a completed session.

        Args:
            session: Completed session to learn from

        Returns:
            List of extracted lessons
        """
        lessons = []

        try:
            # Learn from error recovery
            if self._had_error_recovery(session):
                error_lessons = self._learn_from_error_recovery(session)
                lessons.extend(error_lessons)

            # Learn from corrections
            if session.corrections:
                correction_lessons = self._learn_from_corrections(session)
                lessons.extend(correction_lessons)

            # Reinforce successful patterns
            if session.final_sql and session.state_machine.current_state == AgentState.COMPLETED:
                self._reinforce_used_lessons(session)

            # Save all lessons
            for lesson in lessons:
                self.repository.add_lesson(lesson, save=False)

            # Save once at the end
            if lessons:
                self.repository.save_learned_lessons()
                logger.info(f"Learned {len(lessons)} lessons from session {session.session_id}")

        except Exception as e:
            logger.error(f"Failed to learn from session {session.session_id}: {e}")

        return lessons

    def _had_error_recovery(self, session: Session) -> bool:
        """Check if session had errors that were successfully recovered."""
        if not session.sql_attempts:
            return False

        # Check if any attempt had an error
        had_error = any(attempt.get("error") for attempt in session.sql_attempts)

        # Check if final attempt was successful
        is_successful = session.state_machine.current_state == AgentState.COMPLETED and session.final_sql

        return had_error and is_successful

    def _learn_from_error_recovery(self, session: Session) -> List:
        """Learn from error → success recovery patterns.

        Common pattern:
        1. Generated SQL with table name "Customers"
        2. Error: "Table `project.dataset.Customers` not found"
        3. Regenerated with "PROD_Customers"
        4. Success!

        Lesson: Customers → PROD_Customers (add PROD_ prefix)
        """
        lessons = []

        try:
            # Analyze SQL attempts
            for i, attempt in enumerate(session.sql_attempts[:-1]):  # Exclude last (successful) attempt
                error = attempt.get("error", "")
                failed_sql = attempt.get("sql", "")

                if "not found" in error.lower() and failed_sql:
                    # Extract table name from error
                    table_pattern = r"Table `[^.]+\.[^.]+\.([^`]+)`"
                    match = re.search(table_pattern, error)

                    if match:
                        failed_table = match.group(1)

                        # Check if next attempt succeeded with different table name
                        if i + 1 < len(session.sql_attempts):
                            next_attempt = session.sql_attempts[i + 1]
                            if not next_attempt.get("error") and next_attempt.get("sql"):
                                successful_sql = next_attempt["sql"]

                                # Try to find the corrected table name
                                successful_table = self._extract_table_from_sql(
                                    successful_sql,
                                    failed_table
                                )

                                if successful_table and successful_table != failed_table:
                                    # Found a mapping!
                                    lesson = self._create_table_mapping_lesson(
                                        schema_name=failed_table,
                                        actual_name=successful_table,
                                        session_id=session.session_id,
                                    )
                                    lessons.append(lesson)
                                    logger.info(
                                        f"Learned table mapping: {failed_table} → {successful_table}"
                                    )

        except Exception as e:
            logger.error(f"Error learning from error recovery: {e}")

        return lessons

    def _learn_from_corrections(self, session: Session) -> List:
        """Learn from user corrections.

        User corrections often contain valuable information like:
        - "Use PROD_ prefix for all tables"
        - "customer_id should be cust_id"
        - "Join on Orders.customer_id = Customers.id"
        """
        lessons = []

        try:
            for correction in session.corrections:
                correction_text = correction.correction_text.lower()

                # Pattern 1: Table prefix corrections
                if "prefix" in correction_text or "prod_" in correction_text:
                    # Extract prefix if mentioned
                    prefix_match = re.search(r'(prod_|dwh_|stg_|[a-z]+_)', correction_text, re.IGNORECASE)
                    if prefix_match:
                        prefix = prefix_match.group(1).upper()

                        # Check if user mentioned specific tables
                        if session.identified_tables:
                            for table in session.identified_tables:
                                if table not in correction_text:  # Only if table not explicitly mentioned
                                    lesson = self._create_table_mapping_lesson(
                                        schema_name=table,
                                        actual_name=prefix + table,
                                        session_id=session.session_id,
                                        confidence=0.7,  # Lower confidence for inferred lessons
                                    )
                                    lessons.append(lesson)

                # Pattern 2: Column mapping corrections
                column_pattern = r'(\w+)\s+(?:should be|is|means)\s+(\w+)'
                matches = re.findall(column_pattern, correction_text)
                for schema_col, actual_col in matches:
                    if session.identified_tables:
                        # Assume applies to first table mentioned
                        table = session.identified_tables[0]
                        lesson = ColumnMappingLesson(
                            id=str(uuid.uuid4()),
                            content=f"In {table}, column '{schema_col}' maps to '{actual_col}'",
                            table_name=table,
                            schema_column=schema_col,
                            actual_column=actual_col,
                            confidence=0.8,
                            source="correction",
                            learned_from_sessions=[session.session_id],
                        )
                        lessons.append(lesson)
                        logger.info(f"Learned column mapping: {table}.{schema_col} → {actual_col}")

        except Exception as e:
            logger.error(f"Error learning from corrections: {e}")

        return lessons

    def _reinforce_used_lessons(self, session: Session):
        """Reinforce lessons that were successfully used in this session.

        When a query succeeds, increase confidence of any lessons that were applied.
        """
        try:
            # Check which lessons were likely used
            if session.identified_tables:
                for table in session.identified_tables:
                    lessons = self.repository.get_table_mapping_lessons(table)
                    for lesson in lessons:
                        # Check if the lesson's transformation appears in final SQL
                        transformed = lesson.apply(table)
                        if transformed and session.final_sql and transformed in session.final_sql:
                            self.repository.update_lesson_stats(
                                lesson.id,
                                successful=True,
                                save=False
                            )
                            logger.debug(f"Reinforced lesson {lesson.id}")

        except Exception as e:
            logger.error(f"Error reinforcing lessons: {e}")

    def _extract_table_from_sql(self, sql: str, base_table: str) -> Optional[str]:
        """Extract the actual table name used in SQL.

        Args:
            sql: SQL query
            base_table: Base table name to look for

        Returns:
            Actual table name or None
        """
        # Look for variations of the table name
        patterns = [
            rf'\bFROM\s+`?[^.]*\.?[^.]*\.?([A-Za-z_][A-Za-z0-9_]*{base_table}[A-Za-z0-9_]*)`?',
            rf'\bJOIN\s+`?[^.]*\.?[^.]*\.?([A-Za-z_][A-Za-z0-9_]*{base_table}[A-Za-z0-9_]*)`?',
        ]

        for pattern in patterns:
            match = re.search(pattern, sql, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _create_table_mapping_lesson(
        self,
        schema_name: str,
        actual_name: str,
        session_id: str,
        confidence: float = 0.8,
    ) -> TableMappingLesson:
        """Create a table mapping lesson.

        Args:
            schema_name: Table name in schema
            actual_name: Actual table name in database
            session_id: Session this was learned from
            confidence: Initial confidence score

        Returns:
            TableMappingLesson
        """
        # Detect prefix
        prefix = None
        if actual_name.startswith(schema_name):
            prefix = actual_name[:-len(schema_name)]
        elif '_' in actual_name:
            parts = actual_name.split('_')
            if schema_name.startswith('_'.join(parts[1:])):
                prefix = parts[0] + '_'

        transformation_rule = None
        if prefix:
            transformation_rule = f"Add '{prefix}' prefix to table names"

        lesson = TableMappingLesson(
            id=str(uuid.uuid4()),
            content=f"Table '{schema_name}' maps to '{actual_name}' in database",
            schema_name=schema_name,
            actual_name=actual_name,
            prefix=prefix,
            transformation_rule=transformation_rule,
            confidence=confidence,
            source="auto_learned",
            learned_from_sessions=[session_id],
            applicable_to=[schema_name],
        )

        return lesson
