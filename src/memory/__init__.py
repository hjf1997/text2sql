"""Cross-session memory system for learning from past queries.

This module provides functionality to:
- Store learned patterns (table mappings, column mappings, etc.)
- Automatically extract lessons from successful/failed queries
- Apply learned transformations to new queries
- Build institutional knowledge over time
"""

from .models import (
    Lesson,
    LessonType,
    TableMappingLesson,
    ColumnMappingLesson,
    ErrorPatternLesson,
    QueryPatternLesson,
)
from .repository import LessonRepository, lesson_repository
from .table_mapper import TableMapper
from .learner import LessonLearner

__all__ = [
    # Models
    "Lesson",
    "LessonType",
    "TableMappingLesson",
    "ColumnMappingLesson",
    "ErrorPatternLesson",
    "QueryPatternLesson",
    # Repository
    "LessonRepository",
    "lesson_repository",
    # Mapper
    "TableMapper",
    # Learner
    "LessonLearner",
]
