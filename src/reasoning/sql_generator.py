"""SQL generation module for creating BigQuery SQL from user requirements."""

import re
from typing import List, Dict, Optional
from ..schema import Schema, JoinCandidate
from ..llm import llm_client, PromptTemplates
from ..core import Session
from ..memory import TableMapper, lesson_repository
from ..utils import setup_logger, ValidationError

logger = setup_logger(__name__)


class SQLGenerator:
    """Generates BigQuery SQL from query understanding and schema."""

    def __init__(self, schema: Schema, apply_memory: bool = True):
        """Initialize SQL generator.

        Args:
            schema: Database schema
            apply_memory: Whether to apply learned transformations (default: True)
        """
        self.schema = schema
        self.apply_memory = apply_memory
        self.table_mapper = TableMapper() if apply_memory else None

    def generate(
        self,
        user_query: str,
        identified_tables: List[str],
        join_conditions: Optional[List[JoinCandidate]] = None,
        constraints: Optional[List[str]] = None,
        exploration_results: Optional[Dict] = None,
        session: Optional[Session] = None,
    ) -> str:
        """Generate SQL query.

        Args:
            user_query: Original user query
            identified_tables: List of table names to use
            join_conditions: Optional join conditions
            constraints: Optional constraints from corrections
            exploration_results: Optional exploration query results
            session: Optional session for tracking

        Returns:
            Generated SQL query string

        Raises:
            ValidationError: If SQL generation fails
        """
        logger.info(f"Generating SQL for query: {user_query}")
        logger.info(f"Using tables: {identified_tables}")

        # Apply learned table transformations
        transformed_tables = identified_tables
        if self.apply_memory and self.table_mapper:
            transformations = self.table_mapper.transform_multiple(identified_tables)
            transformed_tables = list(transformations.values())

            # Log transformations
            for original, transformed in transformations.items():
                if original != transformed:
                    logger.info(f"Applied memory: {original} → {transformed}")

        # Get relevant lessons for context
        lessons = []
        if self.apply_memory:
            lessons = lesson_repository.get_relevant_lessons(
                user_query=user_query,
                identified_tables=identified_tables,
            )
            logger.info(f"Retrieved {len(lessons)} relevant lessons")

        # Generate SQL prompt with lessons
        prompt = PromptTemplates.sql_generation(
            user_query,
            self.schema,
            transformed_tables,  # Use transformed table names
            join_conditions,
            constraints,
            exploration_results,
            lessons=lessons,  # Include lessons
        )

        # Get LLM response
        response = llm_client.chat_completion(
            messages=[
                {"role": "system", "content": PromptTemplates.system_message()},
                {"role": "user", "content": prompt},
            ],
            session=session,
            temperature=0.0,  # Use deterministic generation for SQL
        )

        # Extract SQL from response
        sql = self._extract_sql(response)

        # Clean SQL
        sql = self._clean_sql(sql)

        logger.info(f"Generated SQL: {sql[:200]}...")

        return sql

    def refine(
        self,
        user_query: str,
        identified_tables: List[str],
        previous_sql: str,
        error_message: str,
        attempt_number: int,
        join_conditions: Optional[List[JoinCandidate]] = None,
        constraints: Optional[List[str]] = None,
        session: Optional[Session] = None,
    ) -> str:
        """Refine SQL query based on previous error.

        Args:
            user_query: Original user query
            identified_tables: List of table names to use
            previous_sql: The SQL that failed
            error_message: Error message from database
            attempt_number: Current attempt number
            join_conditions: Optional join conditions
            constraints: Optional constraints from corrections
            session: Optional session for tracking

        Returns:
            Refined SQL query string

        Raises:
            ValidationError: If SQL refinement fails
        """
        logger.info(f"Refining SQL (attempt {attempt_number}) based on error: {error_message[:100]}...")

        # Apply learned table transformations
        transformed_tables = identified_tables
        if self.apply_memory and self.table_mapper:
            transformations = self.table_mapper.transform_multiple(identified_tables)
            transformed_tables = list(transformations.values())

            # Log transformations
            for original, transformed in transformations.items():
                if original != transformed:
                    logger.info(f"Applied memory: {original} → {transformed}")

        # Get relevant lessons for context
        lessons = []
        if self.apply_memory:
            lessons = lesson_repository.get_relevant_lessons(
                user_query=user_query,
                identified_tables=identified_tables,
            )
            logger.info(f"Retrieved {len(lessons)} relevant lessons for refinement")

        # Generate SQL refinement prompt with error context
        prompt = PromptTemplates.sql_refinement(
            user_query,
            self.schema,
            transformed_tables,  # Use transformed table names
            previous_sql,
            error_message,
            attempt_number,
            join_conditions,
            constraints,
            lessons=lessons,  # Include lessons
        )

        # Get LLM response
        response = llm_client.chat_completion(
            messages=[
                {"role": "system", "content": PromptTemplates.system_message()},
                {"role": "user", "content": prompt},
            ],
            session=session,
            temperature=0.0,  # Use deterministic generation for SQL
        )

        # Extract SQL from response
        sql = self._extract_sql(response)

        # Clean SQL
        sql = self._clean_sql(sql)

        logger.info(f"Refined SQL (attempt {attempt_number}): {sql[:200]}...")

        return sql

    def _extract_sql(self, response: str) -> str:
        """Extract SQL query from LLM response.

        Args:
            response: LLM response text

        Returns:
            Extracted SQL query

        Raises:
            ValidationError: If no SQL found in response
        """
        # Try to find SQL in code blocks first
        code_block_match = re.search(
            r"```(?:sql)?\s*\n(.*?)\n```",
            response,
            re.IGNORECASE | re.DOTALL
        )
        if code_block_match:
            return code_block_match.group(1).strip()

        # Look for SELECT statements
        select_match = re.search(
            r"(SELECT\s+.+?)(?:;|\n\n|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )
        if select_match:
            return select_match.group(1).strip()

        # If all else fails, try to find anything that looks like SQL
        # Look for lines that contain SQL keywords
        lines = response.split('\n')
        sql_lines = []
        in_sql = False

        for line in lines:
            line_upper = line.upper().strip()
            if any(keyword in line_upper for keyword in ['SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY', 'ORDER BY']):
                in_sql = True

            if in_sql:
                sql_lines.append(line)

                # Stop if we hit a semicolon
                if ';' in line:
                    break

        if sql_lines:
            return '\n'.join(sql_lines).strip()

        # No SQL found
        raise ValidationError(
            f"Could not extract SQL from LLM response. "
            f"Response: {response[:500]}"
        )

    def _clean_sql(self, sql: str) -> str:
        """Clean and format SQL query.

        Args:
            sql: Raw SQL query

        Returns:
            Cleaned SQL query
        """
        # Remove trailing semicolon if present
        sql = sql.rstrip(';').strip()

        # Remove markdown artifacts
        sql = sql.replace('```sql', '').replace('```', '')

        # Remove excessive whitespace
        sql = re.sub(r'\s+', ' ', sql)

        # Add newlines for readability at major keywords
        sql = re.sub(
            r'\s+(FROM|WHERE|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|GROUP BY|ORDER BY|HAVING|LIMIT)',
            r'\n\1',
            sql,
            flags=re.IGNORECASE
        )

        return sql.strip()
