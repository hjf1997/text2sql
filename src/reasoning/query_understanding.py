"""Query understanding module for identifying tables and columns from user queries."""

from typing import List, Dict, Optional
from ..schema import Schema
from ..llm import llm_client, PromptTemplates
from ..core import Session
from ..utils import setup_logger
from .output_schemas import QueryUnderstandingOutput

logger = setup_logger(__name__)


class QueryUnderstanding:
    """Analyzes user queries to identify required tables and columns."""

    def __init__(self, schema: Schema):
        """Initialize query understanding.

        Args:
            schema: Database schema
        """
        self.schema = schema

    def analyze(
        self,
        user_query: str,
        session: Optional[Session] = None,
    ) -> Dict[str, any]:
        """Analyze user query to identify tables, columns, and requirements.

        Args:
            user_query: Natural language query
            session: Optional session for tracking

        Returns:
            Dictionary containing:
                - tables: List of table names
                - columns: List of column names (table.column)
                - joins_needed: Boolean
                - filters: Description of filters needed
                - aggregations: Description of aggregations needed
                - ordering: Description of ordering requirements
                - reasoning: Explanation of the analysis
        """
        logger.info(f"Analyzing query: {user_query}")

        # Generate understanding prompt
        prompt = PromptTemplates.query_understanding(user_query, self.schema)

        # Use with_structured_output for automatic schema enforcement
        try:
            output = llm_client.with_structured_output(
                schema=QueryUnderstandingOutput,
                messages=[
                    {"role": "system", "content": PromptTemplates.system_message()},
                    {"role": "user", "content": prompt},
                ],
                session=session,
            )

            # Validate tables against schema
            valid_tables = [
                t for t in output.tables
                if self.schema.get_table(t)
            ]

            if len(valid_tables) < len(output.tables):
                invalid_tables = set(output.tables) - set(valid_tables)
                logger.warning(
                    f"Some tables not found in schema: {invalid_tables}"
                )

            # Convert to dictionary
            understanding = {
                "tables": valid_tables,
                "columns": output.columns,
                "joins_needed": output.joins_needed,
                "filters": output.filters,
                "aggregations": output.aggregations,
                "ordering": output.ordering,
                "reasoning": output.reasoning,
            }

            logger.info(
                f"Identified {len(understanding['tables'])} table(s): "
                f"{understanding['tables']}"
            )

            return understanding

        except Exception as e:
            logger.error(f"Query understanding failed: {str(e)}")
            # Return empty understanding as fallback
            return {
                "tables": [],
                "columns": [],
                "joins_needed": False,
                "filters": None,
                "aggregations": None,
                "ordering": None,
                "reasoning": f"Error: {str(e)}",
            }

