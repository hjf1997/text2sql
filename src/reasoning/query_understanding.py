"""Query understanding module for identifying tables and columns from user queries."""

from typing import List, Dict, Optional
from difflib import SequenceMatcher
from ..schema import Schema
from ..llm import llm_client, PromptTemplates
from ..core import Session
from ..correction.models import CorrectionType
from ..utils import setup_logger, AmbiguityError
from ..config import settings
from .output_schemas import (
    QueryUnderstandingOutput,
    TableRelevanceOutput,
    TableRefinementOutput,
)

logger = setup_logger(__name__)


class QueryUnderstanding:
    """Analyzes user queries to identify required tables and columns."""

    def __init__(self, schema: Schema, ambiguity_threshold: Optional[float] = None, apply_memory: bool = True):
        """Initialize query understanding.

        Args:
            schema: Database schema
            ambiguity_threshold: Similarity threshold for detecting ambiguous tables (0.0-1.0)
            apply_memory: Whether to apply learned lessons (default: True)
        """
        self.schema = schema
        self.ambiguity_threshold = ambiguity_threshold or settings.get(
            "agent.table_ambiguity_threshold", 0.7
        )
        self.apply_memory = apply_memory

    def analyze(
        self,
        user_query: str,
        session: Optional[Session] = None,
    ) -> Dict[str, any]:
        """Analyze user query to identify tables, columns, and requirements using three-phase approach.

        Phase 1: Iterative table evaluation (one table at a time)
        Phase 2: Refinement (review all selected tables together)
        Phase 3: Requirements synthesis (joins, filters, aggregations)

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

        try:
            # Retrieve LLM-guided lessons for table identification
            llm_guided_lessons = []
            if self.apply_memory:
                from ..memory import lesson_repository
                llm_guided_lessons = lesson_repository.get_llm_guided_lessons(
                    scope="table_identification"
                )
                logger.info(f"Retrieved {len(llm_guided_lessons)} LLM-guided lessons for table identification")

            # Apply corrections first to filter tables
            tables_to_evaluate, has_table_corrections = self._filter_tables_by_corrections(session)

            # PHASE 1: Evaluate each table individually
            logger.info(f"Phase 1: Evaluating {len(tables_to_evaluate)} tables individually")
            candidate_tables = []
            table_columns_map = {}
            table_relevance_details = []

            for i, table_name in enumerate(tables_to_evaluate, 1):
                table = self.schema.get_table(table_name)
                if not table:
                    logger.warning(f"Table {table_name} not found in schema")
                    continue

                logger.info(f"[{i}/{len(tables_to_evaluate)}] Evaluating table: {table_name}")

                try:
                    # Generate prompt for this specific table
                    prompt = PromptTemplates.table_relevance_evaluation(
                        user_query=user_query,
                        table=table,
                        already_selected_tables=candidate_tables,
                        lessons=llm_guided_lessons
                    )

                    # Call LLM for structured output
                    relevance_output = llm_client.with_structured_output(
                        schema=TableRelevanceOutput,
                        messages=[
                            {"role": "system", "content": PromptTemplates.system_message()},
                            {"role": "user", "content": prompt},
                        ],
                        session=session,
                    )

                    # Store details for reasoning
                    table_relevance_details.append({
                        "table": table_name,
                        "is_relevant": relevance_output.is_relevant,
                        "confidence": relevance_output.confidence,
                        "reasoning": relevance_output.reasoning,
                    })

                    # Add to candidate tables if LLM says so
                    if relevance_output.is_relevant:
                        candidate_tables.append(table_name)
                        table_columns_map[table_name] = relevance_output.relevant_columns

                        logger.info(
                            f"  ✓ RELEVANT (confidence: {relevance_output.confidence:.2f})"
                        )
                    else:
                        logger.info(
                            f"  ✗ Not relevant (confidence: {relevance_output.confidence:.2f})"
                        )

                except Exception as e:
                    logger.error(f"Error evaluating table {table_name}: {str(e)}")
                    # Continue with other tables
                    continue

            # Check if we found any tables
            if not candidate_tables:
                logger.warning("No relevant tables identified in Phase 1")
                return {
                    "tables": [],
                    "columns": [],
                    "joins_needed": False,
                    "filters": None,
                    "aggregations": None,
                    "ordering": None,
                    "reasoning": "No relevant tables found for the query",
                }

            logger.info(
                f"Phase 1 complete: {len(candidate_tables)} candidate table(s) identified: "
                f"{candidate_tables}"
            )

            # PHASE 2: Refine by reviewing all selected tables together
            logger.info(f"Phase 2: Refining {len(candidate_tables)} candidate tables")
            final_tables = candidate_tables
            refinement_reasoning = ""

            if len(candidate_tables) > 1:
                # Only run refinement if multiple tables selected
                try:
                    refinement_prompt = PromptTemplates.table_refinement(
                        user_query=user_query,
                        schema=self.schema,
                        selected_tables=candidate_tables
                    )

                    refinement_output = llm_client.with_structured_output(
                        schema=TableRefinementOutput,
                        messages=[
                            {"role": "system", "content": PromptTemplates.system_message()},
                            {"role": "user", "content": refinement_prompt},
                        ],
                        session=session,
                    )

                    final_tables = refinement_output.final_tables
                    refinement_reasoning = refinement_output.reasoning

                    # Update table_columns_map to only include final tables
                    table_columns_map = {
                        t: table_columns_map.get(t, [])
                        for t in final_tables
                        if t in table_columns_map
                    }

                    if refinement_output.removed_tables:
                        logger.info(
                            f"  Removed tables during refinement: {refinement_output.removed_tables}"
                        )

                    logger.info(f"Phase 2 complete: {len(final_tables)} final table(s): {final_tables}")

                except Exception as e:
                    logger.error(f"Error in refinement phase: {str(e)}")
                    logger.warning("Using candidate tables from Phase 1 without refinement")
                    refinement_reasoning = f"Refinement phase failed: {str(e)}"
            else:
                logger.info("Phase 2 skipped: Only one candidate table")
                refinement_reasoning = "Single table selected, no refinement needed"

            # PHASE 3: Synthesize query requirements
            logger.info(f"Phase 3: Synthesizing requirements for {len(final_tables)} table(s)")
            try:
                synthesis_prompt = PromptTemplates.query_requirements_synthesis(
                    user_query=user_query,
                    relevant_tables=final_tables,
                    table_columns_map=table_columns_map
                )

                synthesis_output = llm_client.with_structured_output(
                    schema=QueryUnderstandingOutput,
                    messages=[
                        {"role": "system", "content": PromptTemplates.system_message()},
                        {"role": "user", "content": synthesis_prompt},
                    ],
                    session=session,
                )

                joins_needed = synthesis_output.joins_needed
                filters = synthesis_output.filters
                aggregations = synthesis_output.aggregations
                ordering = synthesis_output.ordering
                synthesis_reasoning = synthesis_output.reasoning

            except Exception as e:
                logger.error(f"Error synthesizing requirements: {str(e)}")
                # Fallback: basic inference
                joins_needed = len(final_tables) > 1
                filters = None
                aggregations = None
                ordering = None
                synthesis_reasoning = f"Synthesis failed, using basic inference: {str(e)}"

            # Build comprehensive reasoning
            reasoning_parts = [
                "=== PHASE 1: Table Evaluation ===",
            ]
            for detail in table_relevance_details:
                status = "✓ SELECTED" if detail["is_relevant"] else "✗ REJECTED"
                reasoning_parts.append(
                    f"{detail['table']}: {status} "
                    f"(confidence: {detail['confidence']:.2f}) - {detail['reasoning']}"
                )

            reasoning_parts.append("\n=== PHASE 2: Refinement ===")
            reasoning_parts.append(refinement_reasoning)

            reasoning_parts.append("\n=== PHASE 3: Requirements ===")
            reasoning_parts.append(synthesis_reasoning)

            combined_reasoning = "\n".join(reasoning_parts)

            # Collect all columns
            all_columns = []
            for table_name, columns in table_columns_map.items():
                all_columns.extend([f"{table_name}.{col}" for col in columns])

            # Check for table selection ambiguity
            # Only check when: multiple tables + no joins needed + no corrections applied
            if (len(final_tables) > 1 and not joins_needed
                and not has_table_corrections):
                logger.warning(
                    f"Table selection ambiguity: {len(final_tables)} tables identified "
                    f"{final_tables} but no joins needed - query should use only one table"
                )
                raise AmbiguityError(
                    f"Multiple tables identified but query does not require joins. "
                    f"Please specify which single table to use.",
                    options=[
                        f"{t} - {next((d['reasoning'] for d in table_relevance_details if d['table'] == t), 'No reason')}"
                        for t in final_tables
                    ],
                    context={
                        "user_query": user_query,
                        "selected_table": final_tables[0],
                        "similar_tables": final_tables,
                        "type": "table_selection",
                    },
                )

            understanding = {
                "tables": final_tables,
                "columns": all_columns,
                "joins_needed": joins_needed,
                "filters": filters,
                "aggregations": aggregations,
                "ordering": ordering,
                "reasoning": combined_reasoning,
            }

            logger.info(
                f"Query understanding complete: {len(understanding['tables'])} table(s): "
                f"{understanding['tables']}"
            )

            return understanding

        except AmbiguityError:
            # Re-raise ambiguity errors so orchestrator can handle them
            raise

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

    def _filter_tables_by_corrections(self, session: Optional[Session]) -> tuple[List[str], bool]:
        """Apply user corrections to determine which tables to evaluate.

        Args:
            session: Optional session with corrections

        Returns:
            Tuple of (list of table names to evaluate, whether corrections were applied)
        """
        # Start with all tables
        tables_to_evaluate = list(self.schema.tables.keys())
        has_corrections = False

        if session and session.corrections:
            table_corrections = [
                c for c in session.corrections
                if c.correction_type == CorrectionType.TABLE_SELECTION
            ]

            if table_corrections:
                has_corrections = True
                selected = []
                rejected = []

                for correction in table_corrections:
                    if correction.content.get("selected_table"):
                        selected.append(correction.content["selected_table"])
                    if correction.content.get("rejected_tables"):
                        rejected.extend(correction.content["rejected_tables"])

                if selected:
                    # Only evaluate selected tables
                    tables_to_evaluate = [t for t in selected if self.schema.get_table(t)]
                    logger.info(f"Using corrected tables: {tables_to_evaluate}")
                elif rejected:
                    # Exclude rejected tables
                    tables_to_evaluate = [
                        t for t in tables_to_evaluate if t not in rejected
                    ]
                    logger.info(f"Excluding rejected tables: {rejected}")

        return tables_to_evaluate, has_corrections

    def _check_table_ambiguity(self, user_query: str, identified_tables: List[str]) -> None:
        """Check if identified tables have ambiguous alternatives in the schema.

        NOTE: This method is currently NOT USED. We trust LLM single-table selections.
        Kept for potential future use if proactive similarity checking is needed.

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

    def _apply_table_corrections(
        self,
        identified_tables: List[str],
        corrections: List,
    ) -> List[str]:
        """Apply table selection corrections to override LLM selections.

        Args:
            identified_tables: Tables identified by LLM
            corrections: User corrections from session

        Returns:
            Corrected table list
        """
        corrected_tables = identified_tables.copy()

        for correction in corrections:
            if correction.correction_type == CorrectionType.TABLE_SELECTION:
                selected = correction.content.get("selected_table")
                rejected = correction.content.get("rejected_tables", [])

                # Remove rejected tables
                corrected_tables = [t for t in corrected_tables if t not in rejected]

                # Add selected table if not present and if it exists in schema
                if selected and selected not in corrected_tables:
                    if self.schema.get_table(selected):
                        corrected_tables.append(selected)
                        logger.info(f"Applied table correction: added '{selected}'")
                    else:
                        logger.warning(
                            f"Table correction specified '{selected}' but table not found in schema"
                        )

                if rejected:
                    logger.info(f"Applied table correction: rejected {rejected}")

        return corrected_tables

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

