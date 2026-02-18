"""Semantic join inference between tables without explicit foreign keys."""

from typing import List, Optional, Tuple
from difflib import SequenceMatcher
from ..schema import Schema, Table, Column, JoinCandidate
from ..llm import llm_client, PromptTemplates
from ..core import Session
from ..config import settings
from ..utils import JoinInferenceError, AmbiguityError, setup_logger
from .output_schemas import JoinInferenceOutput

logger = setup_logger(__name__)


class JoinInference:
    """Infers join conditions between tables using semantic analysis."""

    def __init__(self, schema: Schema, confidence_threshold: Optional[float] = None):
        """Initialize join inference.

        Args:
            schema: Database schema
            confidence_threshold: Minimum confidence for accepting a join (0.0-1.0)
        """
        self.schema = schema
        self.confidence_threshold = confidence_threshold or settings.get(
            "agent.confidence_threshold", 0.75
        )

    def infer_joins(
        self,
        table1: str,
        table2: str,
        constraints: Optional[List[str]] = None,
        session: Optional[Session] = None,
    ) -> List[JoinCandidate]:
        """Infer possible joins between two tables.

        Args:
            table1: First table name
            table2: Second table name
            constraints: Optional constraints from user corrections
            session: Optional session for tracking

        Returns:
            List of join candidates ordered by confidence

        Raises:
            JoinInferenceError: If join inference fails
            AmbiguityError: If multiple equally valid joins exist
        """
        logger.info(f"Inferring joins between {table1} and {table2}")

        # Get tables from schema
        table1_obj = self.schema.get_table(table1)
        table2_obj = self.schema.get_table(table2)

        if not table1_obj:
            raise JoinInferenceError(f"Table not found in schema: {table1}")
        if not table2_obj:
            raise JoinInferenceError(f"Table not found in schema: {table2}")

        # First, try lexical/heuristic matching
        heuristic_joins = self._heuristic_join_inference(table1_obj, table2_obj)

        # If we have constraints or low-confidence heuristic results, use LLM
        if constraints or not heuristic_joins or heuristic_joins[0].confidence < self.confidence_threshold:
            llm_joins = self._llm_join_inference(
                table1, table2, constraints, session
            )

            # Merge results (LLM takes precedence)
            if llm_joins:
                joins = llm_joins
            else:
                joins = heuristic_joins
        else:
            joins = heuristic_joins

        if not joins:
            raise JoinInferenceError(
                f"Could not infer any join between {table1} and {table2}"
            )

        # Check for ambiguity
        if len(joins) > 1:
            # Check if multiple joins have similar high confidence
            top_confidence = joins[0].confidence
            ambiguous_joins = [
                j for j in joins
                if abs(j.confidence - top_confidence) < 0.1 and j.confidence > 0.7
            ]

            if len(ambiguous_joins) > 1:
                # Ambiguity detected
                logger.warning(f"Ambiguous joins detected between {table1} and {table2}")
                raise AmbiguityError(
                    f"Multiple possible joins found between {table1} and {table2}",
                    options=[str(j) for j in ambiguous_joins],
                    context={
                        "table1": table1,
                        "table2": table2,
                        "joins": [j.to_dict() for j in ambiguous_joins],
                    },
                )

        logger.info(f"Inferred {len(joins)} join(s), top confidence: {joins[0].confidence:.2f}")
        return joins

    def _heuristic_join_inference(
        self,
        table1: Table,
        table2: Table,
    ) -> List[JoinCandidate]:
        """Use heuristic rules to infer joins.

        Args:
            table1: First table
            table2: Second table

        Returns:
            List of join candidates
        """
        candidates = []

        for col1 in table1.columns:
            for col2 in table2.columns:
                # Check if data types are compatible
                if not self._are_types_compatible(col1, col2):
                    continue

                # Calculate similarity and confidence
                confidence = self._calculate_join_confidence(col1, col2, table1, table2)

                if confidence > 0.5:  # Minimum threshold for heuristic
                    candidate = JoinCandidate(
                        left_table=table1.name,
                        right_table=table2.name,
                        left_column=col1.name,
                        right_column=col2.name,
                        confidence=confidence,
                        reasoning=self._generate_reasoning(col1, col2),
                    )
                    candidates.append(candidate)

        # Sort by confidence descending
        candidates.sort(key=lambda x: x.confidence, reverse=True)

        return candidates

    def _llm_join_inference(
        self,
        table1: str,
        table2: str,
        constraints: Optional[List[str]],
        session: Optional[Session],
    ) -> List[JoinCandidate]:
        """Use LLM to infer joins with semantic understanding.

        Args:
            table1: First table name
            table2: Second table name
            constraints: Optional constraints
            session: Optional session

        Returns:
            List of join candidates
        """
        logger.info("Using LLM for semantic join inference")

        # Generate prompt
        prompt = PromptTemplates.join_inference(
            table1, table2, self.schema, constraints
        )

        # Use with_structured_output for automatic schema enforcement
        try:
            output = llm_client.with_structured_output(
                schema=JoinInferenceOutput,
                messages=[
                    {"role": "system", "content": PromptTemplates.system_message()},
                    {"role": "user", "content": prompt},
                ],
                session=session,
            )

            # Check if any joins were found
            if not output.found_joins or not output.joins:
                logger.info("No joins found by LLM")
                return []

            # Convert to JoinCandidate objects
            joins = []
            for join_output in output.joins:
                joins.append(JoinCandidate(
                    left_table=table1,
                    right_table=table2,
                    left_column=join_output.left_column,
                    right_column=join_output.right_column,
                    confidence=join_output.confidence,
                    reasoning=join_output.reasoning,
                ))

            # Sort by confidence
            joins.sort(key=lambda x: x.confidence, reverse=True)

            logger.info(f"Parsed {len(joins)} join(s) from LLM response")
            return joins

        except Exception as e:
            logger.error(f"LLM join inference failed: {str(e)}")
            return []


    def _calculate_join_confidence(
        self,
        col1: Column,
        col2: Column,
        table1: Table,
        table2: Table,
    ) -> float:
        """Calculate confidence score for a potential join.

        Args:
            col1: Column from table1
            col2: Column from table2
            table1: First table
            table2: Second table

        Returns:
            Confidence score (0.0 to 1.0)
        """
        score = 0.0
        factors = []

        # Factor 1: Column name similarity (40% weight)
        name_similarity = self._string_similarity(col1.name, col2.name)
        score += name_similarity * 0.4
        factors.append(f"name_sim={name_similarity:.2f}")

        # Factor 2: Business name similarity (25% weight)
        if col1.business_name and col2.business_name:
            business_similarity = self._string_similarity(
                col1.business_name, col2.business_name
            )
            score += business_similarity * 0.25
            factors.append(f"business_sim={business_similarity:.2f}")

        # Factor 3: Primary key indicators (20% weight)
        if col1.is_primary or col2.is_primary:
            score += 0.2
            factors.append("has_primary_key")

        # Factor 4: Common naming patterns (15% weight)
        if self._has_fk_pattern(col1, table2) or self._has_fk_pattern(col2, table1):
            score += 0.15
            factors.append("fk_pattern")

        logger.debug(f"Join confidence for {col1.name}-{col2.name}: {score:.2f} ({', '.join(factors)})")
        return min(score, 1.0)

    def _string_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Normalize strings
        s1 = str1.lower().replace('_', '').replace(' ', '')
        s2 = str2.lower().replace('_', '').replace(' ', '')

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, s1, s2).ratio()

    def _are_types_compatible(self, col1: Column, col2: Column) -> bool:
        """Check if two column types are compatible for joining.

        Args:
            col1: First column
            col2: Second column

        Returns:
            True if types are compatible
        """
        from ..schema import ColumnType

        # Same type is always compatible
        if col1.data_type == col2.data_type:
            return True

        # Define compatible type groups
        compatible_groups = [
            {ColumnType.INTEGER, ColumnType.NUMERIC, ColumnType.FLOAT},
            {ColumnType.STRING},
            {ColumnType.DATE, ColumnType.DATETIME, ColumnType.TIMESTAMP},
        ]

        for group in compatible_groups:
            if col1.data_type in group and col2.data_type in group:
                return True

        return False

    def _has_fk_pattern(self, column: Column, referenced_table: Table) -> bool:
        """Check if column name follows foreign key naming pattern.

        Args:
            column: Column to check
            referenced_table: Table that might be referenced

        Returns:
            True if column follows FK pattern
        """
        col_name_lower = column.name.lower()
        table_name_lower = referenced_table.name.lower()

        # Common patterns: table_id, tableid, table_name, fk_table
        patterns = [
            f"{table_name_lower}_id",
            f"{table_name_lower}id",
            f"{table_name_lower}_key",
            f"fk_{table_name_lower}",
        ]

        return any(pattern in col_name_lower for pattern in patterns)

    def _generate_reasoning(self, col1: Column, col2: Column) -> str:
        """Generate reasoning text for a join.

        Args:
            col1: First column
            col2: Second column

        Returns:
            Reasoning text
        """
        reasons = []

        if self._string_similarity(col1.name, col2.name) > 0.8:
            reasons.append("column names are very similar")

        if col1.business_name and col2.business_name:
            if self._string_similarity(col1.business_name, col2.business_name) > 0.8:
                reasons.append("business names match")

        if col1.is_primary or col2.is_primary:
            reasons.append("involves primary key")

        if col1.data_type == col2.data_type:
            reasons.append(f"same data type ({col1.data_type.value})")

        if reasons:
            return "Join suggested because: " + "; ".join(reasons)
        return "Heuristic match based on column analysis"
