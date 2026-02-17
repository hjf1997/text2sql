"""Data models for cross-session memory."""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class LessonType(str, Enum):
    """Types of lessons that can be learned."""

    TABLE_MAPPING = "table_mapping"
    COLUMN_MAPPING = "column_mapping"
    ERROR_PATTERN = "error_pattern"
    QUERY_PATTERN = "query_pattern"
    JOIN_PATTERN = "join_pattern"


class Lesson(BaseModel):
    """Base lesson model."""

    id: str
    type: LessonType
    content: str  # Human-readable description
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    source: str = "auto_learned"  # "manual", "auto_learned", "correction"

    # Metadata
    learned_from_sessions: List[str] = Field(default_factory=list)
    applicable_to: List[str] = Field(default_factory=list)  # Tables, patterns, etc.

    # Statistics
    times_retrieved: int = 0
    times_applied: int = 0
    times_successful: int = 0

    # Temporal
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: datetime = Field(default_factory=datetime.utcnow)
    last_validated: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.times_applied == 0:
            return 0.0
        return self.times_successful / self.times_applied

    def record_usage(self, successful: bool = True):
        """Record that this lesson was applied."""
        self.times_applied += 1
        if successful:
            self.times_successful += 1
        self.last_used = datetime.utcnow()

        # Update confidence based on success
        if successful:
            self.confidence = min(1.0, self.confidence + 0.02)
        else:
            self.confidence = max(0.0, self.confidence - 0.05)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "confidence": self.confidence,
            "source": self.source,
            "learned_from_sessions": self.learned_from_sessions,
            "applicable_to": self.applicable_to,
            "times_retrieved": self.times_retrieved,
            "times_applied": self.times_applied,
            "times_successful": self.times_successful,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
        }


class TableMappingLesson(Lesson):
    """Lesson about table name transformations."""

    type: LessonType = LessonType.TABLE_MAPPING
    schema_name: str  # Name in Excel schema
    actual_name: str  # Name in BigQuery
    prefix: Optional[str] = None  # e.g., "PROD_"
    pattern: Optional[str] = None  # Regex pattern for matching
    transformation_rule: Optional[str] = None  # Description of transformation

    def apply(self, table_name: str) -> Optional[str]:
        """Apply this lesson to transform a table name."""
        if table_name == self.schema_name:
            return self.actual_name

        # Check pattern matching
        if self.pattern:
            import re
            if re.match(self.pattern, table_name):
                if self.prefix:
                    return self.prefix + table_name
                return self.actual_name

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "schema_name": self.schema_name,
            "actual_name": self.actual_name,
            "prefix": self.prefix,
            "pattern": self.pattern,
            "transformation_rule": self.transformation_rule,
        })
        return data


class ColumnMappingLesson(Lesson):
    """Lesson about column name mappings."""

    type: LessonType = LessonType.COLUMN_MAPPING
    table_name: str
    schema_column: str  # Name in Excel schema
    actual_column: str  # Name in BigQuery
    data_type: Optional[str] = None
    context: Optional[str] = None

    def apply(self, table: str, column: str) -> Optional[str]:
        """Apply this lesson to transform a column name."""
        if table == self.table_name and column == self.schema_column:
            return self.actual_column
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "table_name": self.table_name,
            "schema_column": self.schema_column,
            "actual_column": self.actual_column,
            "data_type": self.data_type,
            "context": self.context,
        })
        return data


class ErrorPatternLesson(Lesson):
    """Lesson about common errors and their solutions."""

    type: LessonType = LessonType.ERROR_PATTERN
    error_type: str  # e.g., "table_not_found", "column_not_found"
    error_pattern: str  # Regex pattern to match error message
    suggested_fix: str  # Human-readable fix suggestion
    examples: List[Dict[str, str]] = Field(default_factory=list)

    def matches_error(self, error_message: str) -> bool:
        """Check if this lesson applies to an error."""
        import re
        return bool(re.search(self.error_pattern, error_message, re.IGNORECASE))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "error_type": self.error_type,
            "error_pattern": self.error_pattern,
            "suggested_fix": self.suggested_fix,
            "examples": self.examples,
        })
        return data


class QueryPatternLesson(Lesson):
    """Lesson about successful query patterns."""

    type: LessonType = LessonType.QUERY_PATTERN
    query_type: str  # e.g., "customer_orders_join"
    sql_template: str  # Template with placeholders
    variables: Dict[str, str] = Field(default_factory=dict)
    when_to_use: str  # Conditions for using this pattern
    required_tables: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "query_type": self.query_type,
            "sql_template": self.sql_template,
            "variables": self.variables,
            "when_to_use": self.when_to_use,
            "required_tables": self.required_tables,
        })
        return data
