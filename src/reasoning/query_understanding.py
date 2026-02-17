"""Query understanding module for identifying tables and columns from user queries."""

import json
import re
from typing import List, Dict, Optional
from ..schema import Schema
from ..llm import azure_client, PromptTemplates
from ..core import Session
from ..utils import setup_logger

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
                - reasoning: Explanation of the analysis
        """
        logger.info(f"Analyzing query: {user_query}")

        # Generate understanding prompt
        prompt = PromptTemplates.query_understanding(user_query, self.schema)

        # Get LLM analysis
        response = azure_client.chat_completion(
            messages=[
                {"role": "system", "content": PromptTemplates.system_message()},
                {"role": "user", "content": prompt},
            ],
            session=session,
        )

        # Parse response
        understanding = self._parse_understanding_response(response)

        logger.info(
            f"Identified {len(understanding['tables'])} table(s): "
            f"{understanding['tables']}"
        )

        return understanding

    def _parse_understanding_response(self, response: str) -> Dict[str, any]:
        """Parse LLM response into structured understanding.

        Args:
            response: LLM response text

        Returns:
            Dictionary with parsed understanding
        """
        understanding = {
            "tables": [],
            "columns": [],
            "joins_needed": False,
            "filters": None,
            "aggregations": None,
            "reasoning": None,
        }

        # Parse tables
        tables_match = re.search(
            r"REQUIRED TABLES:\s*\[?([^\]\n]+)\]?",
            response,
            re.IGNORECASE
        )
        if tables_match:
            tables_text = tables_match.group(1)
            # Extract table names (split by comma and clean)
            tables = [t.strip().strip('"\'') for t in tables_text.split(',')]
            # Filter out empty strings and validate against schema
            understanding["tables"] = [
                t for t in tables
                if t and self.schema.get_table(t)
            ]

        # Parse columns
        columns_match = re.search(
            r"REQUIRED COLUMNS:\s*\[?([^\]\n]+)\]?",
            response,
            re.IGNORECASE
        )
        if columns_match:
            columns_text = columns_match.group(1)
            columns = [c.strip().strip('"\'') for c in columns_text.split(',')]
            understanding["columns"] = [c for c in columns if c]

        # Parse joins needed
        joins_match = re.search(
            r"JOINS NEEDED:\s*(\w+)",
            response,
            re.IGNORECASE
        )
        if joins_match:
            understanding["joins_needed"] = joins_match.group(1).lower() in ["yes", "true", "y"]

        # Parse filters
        filters_match = re.search(
            r"FILTERS:\s*(.+?)(?=\n[A-Z]+:|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )
        if filters_match:
            understanding["filters"] = filters_match.group(1).strip()

        # Parse aggregations
        agg_match = re.search(
            r"AGGREGATIONS:\s*(.+?)(?=\n[A-Z]+:|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )
        if agg_match:
            understanding["aggregations"] = agg_match.group(1).strip()

        # Parse reasoning
        reasoning_match = re.search(
            r"REASONING:\s*(.+?)$",
            response,
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            understanding["reasoning"] = reasoning_match.group(1).strip()

        return understanding
