"""Query understanding module for identifying tables and columns from user queries."""

from typing import List, Dict, Optional
from difflib import SequenceMatcher
from ..schema import Schema
from ..llm import llm_client, PromptTemplates
from ..core import Session
from ..utils import setup_logger, AmbiguityError
from ..config import settings
from .output_schemas import QueryUnderstandingOutput

logger = setup_logger(__name__)


class QueryUnderstanding:
    """Analyzes user queries to identify required tables and columns."""

    def __init__(self, schema: Schema, ambiguity_threshold: Optional[float] = None):
        """Initialize query understanding.

        Args:
            schema: Database schema
            ambiguity_threshold: Similarity threshold for detecting ambiguous tables (0.0-1.0)
        """
        self.schema = schema
        self.ambiguity_threshold = ambiguity_threshold or settings.get(
            "agent.table_ambiguity_threshold", 0.7
        )

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

            # Check for table selection ambiguity
            self._check_table_ambiguity(user_query, valid_tables)

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

    def _check_table_ambiguity(self, user_query: str, identified_tables: List[str]) -> None:
        """Check if identified tables have ambiguous alternatives in the schema.

        Args:
            user_query: The user's query
            identified_tables: Tables identified by LLM

        Raises:
            AmbiguityError: If ambiguous table alternatives exist
        """
        for table in identified_tables:
            # Find similar tables in schema
            similar_tables = self._find_similar_tables(table)

            if len(similar_tables) > 1:
                # Multiple similar tables found
                logger.warning(
                    f"Ambiguous table selection: '{table}' has {len(similar_tables)} similar alternatives"
                )

                raise AmbiguityError(
                    f"Multiple similar tables found for '{table}'. Please specify which table to use.",
                    options=[f"{t['name']} - {t['reason']}" for t in similar_tables],
                    context={
                        "user_query": user_query,
                        "selected_table": table,
                        "similar_tables": [t["name"] for t in similar_tables],
                        "type": "table_selection",
                    },
                )

    def _find_similar_tables(self, table_name: str) -> List[Dict[str, any]]:
        """Find tables in schema similar to the given table name.

        Args:
            table_name: Table name to find similar matches for

        Returns:
            List of similar tables with similarity info
        """
        similar_tables = []
        # schema.tables is a dict, iterate over values to get Table objects
        all_table_names = [t.name for t in self.schema.tables.values()]

        for schema_table_name in all_table_names:
            # Calculate similarity
            similarity = self._calculate_table_similarity(table_name, schema_table_name)

            # Check if similarity exceeds threshold
            if similarity >= self.ambiguity_threshold:
                reason = self._explain_similarity(table_name, schema_table_name, similarity)

                similar_tables.append({
                    "name": schema_table_name,
                    "similarity": similarity,
                    "reason": reason,
                })

        # Sort by similarity (highest first)
        similar_tables.sort(key=lambda x: x["similarity"], reverse=True)

        return similar_tables

    def _calculate_table_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two table names.

        Args:
            name1: First table name
            name2: Second table name

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Normalize names (lowercase, remove common prefixes)
        norm1 = self._normalize_table_name(name1)
        norm2 = self._normalize_table_name(name2)

        # Calculate base similarity
        base_similarity = SequenceMatcher(None, norm1, norm2).ratio()

        # Exact match bonus
        if name1.lower() == name2.lower():
            return 1.0

        # Substring match bonus
        if norm1 in norm2 or norm2 in norm1:
            base_similarity = max(base_similarity, 0.8)

        return base_similarity

    def _normalize_table_name(self, name: str) -> str:
        """Normalize table name for comparison.

        Args:
            name: Table name

        Returns:
            Normalized name
        """
        # Common prefixes to remove
        prefixes = ["prod_", "dwh_", "stg_", "tmp_", "dev_", "test_"]

        name_lower = name.lower()
        for prefix in prefixes:
            if name_lower.startswith(prefix):
                name_lower = name_lower[len(prefix):]
                break

        return name_lower

    def _explain_similarity(self, name1: str, name2: str, similarity: float) -> str:
        """Generate explanation for why two table names are similar.

        Args:
            name1: First table name
            name2: Second table name
            similarity: Similarity score

        Returns:
            Explanation string
        """
        if name1.lower() == name2.lower():
            return "Exact match"

        norm1 = self._normalize_table_name(name1)
        norm2 = self._normalize_table_name(name2)

        if norm1 == norm2:
            return f"Same base name (different prefixes)"

        if norm1 in norm2 or norm2 in norm1:
            return f"Base name contains match"

        if similarity > 0.85:
            return f"Very similar names (similarity: {similarity:.0%})"

        return f"Similar names (similarity: {similarity:.0%})"

