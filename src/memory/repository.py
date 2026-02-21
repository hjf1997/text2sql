"""Repository for managing lessons learned."""

import yaml
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid

from .models import (
    Lesson,
    LessonType,
    TableMappingLesson,
    ColumnMappingLesson,
    ErrorPatternLesson,
    QueryPatternLesson,
    LLMGuidedLesson,
)
from ..config import settings
from ..utils import setup_logger

logger = setup_logger(__name__)


class LessonRepository:
    """Repository for storing and retrieving lessons."""

    def __init__(self, config_path: Optional[str] = None, learned_path: Optional[str] = None):
        """Initialize the lesson repository.

        Args:
            config_path: Path to manual lessons config file (YAML)
            learned_path: Path to auto-learned lessons file (JSON)
        """
        self.config_path = Path(config_path or "config/lessons_learned.yaml")
        self.learned_path = Path(learned_path or "memory/learned_lessons.json")

        # Ensure directories exist
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.learned_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._manual_lessons: List[Lesson] = []
        self._learned_lessons: List[Lesson] = []

        # Load lessons
        self._load_manual_lessons()
        self._load_learned_lessons()

        logger.info(
            f"Loaded {len(self._manual_lessons)} manual lessons "
            f"and {len(self._learned_lessons)} learned lessons"
        )

    def _load_manual_lessons(self):
        """Load manually configured lessons from YAML."""
        if not self.config_path.exists():
            logger.warning(f"Manual lessons file not found: {self.config_path}")
            return

        try:
            with open(self.config_path, 'r') as f:
                data = yaml.safe_load(f) or {}

            # Load table mappings
            for mapping in data.get("table_mappings", []):
                lesson = TableMappingLesson(
                    id=mapping.get("id", str(uuid.uuid4())),
                    content=mapping.get("content", ""),
                    schema_name=mapping.get("schema_name", ""),
                    actual_name=mapping.get("actual_name", ""),
                    prefix=mapping.get("prefix"),
                    pattern=mapping.get("pattern"),
                    transformation_rule=mapping.get("transformation_rule"),
                    confidence=mapping.get("confidence", 0.95),
                    source="manual",
                    applicable_to=mapping.get("applicable_to", []),
                )
                self._manual_lessons.append(lesson)

            # Load column mappings
            for mapping in data.get("column_mappings", []):
                lesson = ColumnMappingLesson(
                    id=mapping.get("id", str(uuid.uuid4())),
                    content=mapping.get("content", ""),
                    table_name=mapping.get("table_name", ""),
                    schema_column=mapping.get("schema_column", ""),
                    actual_column=mapping.get("actual_column", ""),
                    data_type=mapping.get("data_type"),
                    context=mapping.get("context"),
                    confidence=mapping.get("confidence", 0.95),
                    source="manual",
                )
                self._manual_lessons.append(lesson)

            # Load error patterns
            for pattern in data.get("error_patterns", []):
                lesson = ErrorPatternLesson(
                    id=pattern.get("id", str(uuid.uuid4())),
                    content=pattern.get("content", ""),
                    error_type=pattern.get("error_type", ""),
                    error_pattern=pattern.get("error_pattern", ""),
                    suggested_fix=pattern.get("suggested_fix", ""),
                    examples=pattern.get("examples", []),
                    confidence=pattern.get("confidence", 0.9),
                    source="manual",
                )
                self._manual_lessons.append(lesson)

            # Load query patterns
            for pattern in data.get("query_patterns", []):
                lesson = QueryPatternLesson(
                    id=pattern.get("id", str(uuid.uuid4())),
                    content=pattern.get("content", ""),
                    query_type=pattern.get("query_type", ""),
                    sql_template=pattern.get("sql_template", ""),
                    variables=pattern.get("variables", {}),
                    when_to_use=pattern.get("when_to_use", ""),
                    required_tables=pattern.get("required_tables", []),
                    confidence=pattern.get("confidence", 0.85),
                    source="manual",
                )
                self._manual_lessons.append(lesson)

            # Load LLM-guided lessons
            for lesson_data in data.get("llm_guided_lessons", []):
                lesson = LLMGuidedLesson(
                    id=lesson_data.get("id", str(uuid.uuid4())),
                    content=lesson_data.get("content", ""),
                    instruction=lesson_data.get("instruction", ""),
                    scope=lesson_data.get("scope", "all"),
                    priority=lesson_data.get("priority", 0),
                    confidence=lesson_data.get("confidence", 0.9),
                    source="manual",
                    applicable_to=lesson_data.get("applicable_to", []),
                )
                self._manual_lessons.append(lesson)

            logger.info(f"Loaded {len(self._manual_lessons)} manual lessons")

        except Exception as e:
            logger.error(f"Failed to load manual lessons: {e}")

    def _load_learned_lessons(self):
        """Load auto-learned lessons from JSON."""
        if not self.learned_path.exists():
            logger.info(f"No learned lessons file found at {self.learned_path}")
            return

        try:
            with open(self.learned_path, 'r') as f:
                data = json.load(f)

            for item in data:
                lesson_type = LessonType(item["type"])

                if lesson_type == LessonType.TABLE_MAPPING:
                    lesson = TableMappingLesson(**item)
                elif lesson_type == LessonType.COLUMN_MAPPING:
                    lesson = ColumnMappingLesson(**item)
                elif lesson_type == LessonType.ERROR_PATTERN:
                    lesson = ErrorPatternLesson(**item)
                elif lesson_type == LessonType.QUERY_PATTERN:
                    lesson = QueryPatternLesson(**item)
                elif lesson_type == LessonType.LLM_GUIDED:
                    lesson = LLMGuidedLesson(**item)
                else:
                    lesson = Lesson(**item)

                self._learned_lessons.append(lesson)

            logger.info(f"Loaded {len(self._learned_lessons)} learned lessons")

        except Exception as e:
            logger.error(f"Failed to load learned lessons: {e}")

    def save_learned_lessons(self):
        """Save auto-learned lessons to JSON."""
        try:
            data = [lesson.to_dict() for lesson in self._learned_lessons]

            with open(self.learned_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(f"Saved {len(self._learned_lessons)} learned lessons")

        except Exception as e:
            logger.error(f"Failed to save learned lessons: {e}")

    def get_all_lessons(self) -> List[Lesson]:
        """Get all lessons (manual + learned)."""
        return self._manual_lessons + self._learned_lessons

    def get_table_mapping_lessons(self, table_name: Optional[str] = None) -> List[TableMappingLesson]:
        """Get table mapping lessons."""
        lessons = [
            l for l in self.get_all_lessons()
            if isinstance(l, TableMappingLesson)
        ]

        if table_name:
            lessons = [
                l for l in lessons
                if l.schema_name == table_name or (l.pattern and self._matches_pattern(table_name, l.pattern))
            ]

        return sorted(lessons, key=lambda x: x.confidence, reverse=True)

    def get_column_mapping_lessons(
        self,
        table_name: Optional[str] = None,
        column_name: Optional[str] = None
    ) -> List[ColumnMappingLesson]:
        """Get column mapping lessons."""
        lessons = [
            l for l in self.get_all_lessons()
            if isinstance(l, ColumnMappingLesson)
        ]

        if table_name:
            lessons = [l for l in lessons if l.table_name == table_name]

        if column_name:
            lessons = [l for l in lessons if l.schema_column == column_name]

        return sorted(lessons, key=lambda x: x.confidence, reverse=True)

    def get_error_pattern_lessons(self, error_message: Optional[str] = None) -> List[ErrorPatternLesson]:
        """Get error pattern lessons, optionally filtered by error message."""
        lessons = [
            l for l in self.get_all_lessons()
            if isinstance(l, ErrorPatternLesson)
        ]

        if error_message:
            lessons = [l for l in lessons if l.matches_error(error_message)]

        return sorted(lessons, key=lambda x: x.confidence, reverse=True)

    def get_relevant_lessons(
        self,
        user_query: Optional[str] = None,
        identified_tables: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Lesson]:
        """Get lessons relevant to a query.

        Args:
            user_query: The user's natural language query
            identified_tables: Tables identified from the query
            context: Additional context (errors, corrections, etc.)

        Returns:
            List of relevant lessons, sorted by relevance and confidence
        """
        relevant = []

        # Get table mapping lessons for identified tables
        if identified_tables:
            for table in identified_tables:
                lessons = self.get_table_mapping_lessons(table)
                relevant.extend(lessons)

        # Get error pattern lessons if there was an error
        if context and context.get("error"):
            error_lessons = self.get_error_pattern_lessons(context["error"])
            relevant.extend(error_lessons)

        # Remove duplicates and sort
        seen = set()
        unique_lessons = []
        for lesson in relevant:
            if lesson.id not in seen:
                seen.add(lesson.id)
                unique_lessons.append(lesson)

        return sorted(unique_lessons, key=lambda x: x.confidence, reverse=True)

    def get_llm_guided_lessons(
        self,
        scope: Optional[str] = None,
        identified_tables: Optional[List[str]] = None,
    ) -> List[LLMGuidedLesson]:
        """Get LLM-guided lessons for a specific scope.

        Args:
            scope: Filter by scope ("table_identification", "sql_generation", or "all")
            identified_tables: Optional tables to filter applicable_to

        Returns:
            List of LLM-guided lessons, sorted by priority (desc) then confidence (desc)
        """
        lessons = [
            l for l in self.get_all_lessons()
            if isinstance(l, LLMGuidedLesson)
        ]

        # Filter by scope
        if scope:
            lessons = [
                l for l in lessons
                if l.scope == "all" or l.scope == scope
            ]

        # Filter by applicable tables
        if identified_tables:
            lessons = [
                l for l in lessons
                if not l.applicable_to or "all" in l.applicable_to
                or any(table in l.applicable_to for table in identified_tables)
            ]

        # Sort by priority (desc), then confidence (desc)
        return sorted(lessons, key=lambda x: (-x.priority, -x.confidence))

    def add_lesson(self, lesson: Lesson, save: bool = True):
        """Add a new learned lesson.

        Args:
            lesson: The lesson to add
            save: Whether to save to disk immediately
        """
        # Check if lesson already exists
        existing = next(
            (l for l in self._learned_lessons if l.id == lesson.id),
            None
        )

        if existing:
            logger.info(f"Updating existing lesson: {lesson.id}")
            # Update existing lesson
            self._learned_lessons.remove(existing)

        self._learned_lessons.append(lesson)
        logger.info(f"Added new lesson: {lesson.type.value} - {lesson.content}")

        if save:
            self.save_learned_lessons()

    def update_lesson_stats(self, lesson_id: str, successful: bool = True, save: bool = True):
        """Update statistics for a lesson after it was applied.

        Args:
            lesson_id: ID of the lesson that was applied
            successful: Whether the application was successful
            save: Whether to save to disk immediately
        """
        # Find lesson (check both manual and learned)
        lesson = next(
            (l for l in self.get_all_lessons() if l.id == lesson_id),
            None
        )

        if lesson:
            lesson.record_usage(successful)
            logger.info(
                f"Updated lesson {lesson_id}: "
                f"success_rate={lesson.success_rate:.2%}, "
                f"confidence={lesson.confidence:.2%}"
            )

            if save and lesson in self._learned_lessons:
                self.save_learned_lessons()

    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """Check if text matches a pattern."""
        import re
        try:
            return bool(re.match(pattern, text))
        except Exception:
            return False


# Global repository instance
lesson_repository = LessonRepository()
