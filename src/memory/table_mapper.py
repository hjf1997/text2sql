"""Table name mapper that applies learned transformations."""

from typing import List, Optional, Dict
from .repository import lesson_repository
from .models import TableMappingLesson
from ..utils import setup_logger

logger = setup_logger(__name__)


class TableMapper:
    """Maps schema table names to actual database table names using learned patterns."""

    def __init__(self, repository=None):
        """Initialize table mapper.

        Args:
            repository: Lesson repository (uses global instance if None)
        """
        self.repository = repository or lesson_repository

    def transform(self, table_name: str, apply_lessons: bool = True) -> str:
        """Transform a table name using learned patterns.

        Args:
            table_name: Original table name from schema
            apply_lessons: Whether to apply learned transformations

        Returns:
            Transformed table name (or original if no transformation found)
        """
        if not apply_lessons:
            return table_name

        # Get relevant table mapping lessons
        lessons = self.repository.get_table_mapping_lessons(table_name)

        if not lessons:
            logger.debug(f"No table mapping lessons found for: {table_name}")
            return table_name

        # Apply the highest confidence lesson
        best_lesson = lessons[0]
        transformed = best_lesson.apply(table_name)

        if transformed and transformed != table_name:
            logger.info(
                f"Transformed table: {table_name} → {transformed} "
                f"(confidence: {best_lesson.confidence:.2%}, "
                f"lesson: {best_lesson.id})"
            )
            return transformed

        return table_name

    def transform_multiple(
        self,
        table_names: List[str],
        apply_lessons: bool = True
    ) -> Dict[str, str]:
        """Transform multiple table names.

        Args:
            table_names: List of table names from schema
            apply_lessons: Whether to apply learned transformations

        Returns:
            Dictionary mapping original names to transformed names
        """
        return {
            table: self.transform(table, apply_lessons)
            for table in table_names
        }

    def get_transformation_info(self, table_name: str) -> Optional[Dict]:
        """Get information about how a table would be transformed.

        Args:
            table_name: Table name to check

        Returns:
            Dictionary with transformation details or None
        """
        lessons = self.repository.get_table_mapping_lessons(table_name)

        if not lessons:
            return None

        best_lesson = lessons[0]
        transformed = best_lesson.apply(table_name)

        if not transformed or transformed == table_name:
            return None

        return {
            "original": table_name,
            "transformed": transformed,
            "lesson_id": best_lesson.id,
            "confidence": best_lesson.confidence,
            "source": best_lesson.source,
            "rule": best_lesson.transformation_rule or best_lesson.content,
            "success_rate": best_lesson.success_rate,
        }

    def preview_transformations(self, table_names: List[str]) -> List[Dict]:
        """Preview how tables would be transformed.

        Args:
            table_names: List of table names

        Returns:
            List of transformation details
        """
        transformations = []

        for table in table_names:
            info = self.get_transformation_info(table)
            if info:
                transformations.append(info)
            else:
                transformations.append({
                    "original": table,
                    "transformed": table,
                    "lesson_id": None,
                    "confidence": 1.0,
                    "source": "none",
                    "rule": "No transformation",
                    "success_rate": 0.0,
                })

        return transformations
