"""Data models for user corrections."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class CorrectionType(Enum):
    """Types of corrections users can provide."""

    JOIN_CLARIFICATION = "join_clarification"
    COLUMN_MAPPING = "column_mapping"
    TABLE_SELECTION = "table_selection"
    FILTER_CLARIFICATION = "filter_clarification"
    BUSINESS_LOGIC = "business_logic"
    NATURAL_LANGUAGE = "natural_language"


@dataclass
class Correction:
    """Represents a user correction to guide the agent."""

    correction_type: CorrectionType
    content: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    attempt_number: int = 0
    description: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert correction to dictionary."""
        return {
            "correction_type": self.correction_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "attempt_number": self.attempt_number,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Correction':
        """Create correction from dictionary."""
        return cls(
            correction_type=CorrectionType(data["correction_type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            attempt_number=data.get("attempt_number", 0),
            description=data.get("description"),
        )

    def to_constraint_string(self) -> str:
        """Convert correction to a constraint string for LLM context."""
        if self.correction_type == CorrectionType.JOIN_CLARIFICATION:
            return (
                f"MANDATORY JOIN: {self.content.get('join_condition')} "
                f"between {self.content.get('tables', [])}"
            )
        elif self.correction_type == CorrectionType.COLUMN_MAPPING:
            return (
                f"COLUMN MAPPING: '{self.content.get('user_term')}' maps to "
                f"'{self.content.get('actual_column')}'"
            )
        elif self.correction_type == CorrectionType.TABLE_SELECTION:
            selected = self.content.get('selected_table')
            rejected = self.content.get('rejected_tables', [])
            if rejected:
                return (
                    f"MANDATORY TABLE: Use table '{selected}'. "
                    f"DO NOT use: {', '.join(rejected)}"
                )
            return f"MANDATORY TABLE: Use table '{selected}'"
        elif self.correction_type == CorrectionType.FILTER_CLARIFICATION:
            return f"FILTER REQUIREMENT: {self.content.get('filter_description')}"
        elif self.correction_type == CorrectionType.BUSINESS_LOGIC:
            return f"BUSINESS LOGIC: {self.content.get('logic_description')}"
        elif self.correction_type == CorrectionType.NATURAL_LANGUAGE:
            return f"USER CLARIFICATION: {self.content.get('correction')}"
        return str(self.content)


@dataclass
class JoinClarification(Correction):
    """Specific correction for join clarification."""

    def __init__(
        self,
        tables: list[str],
        join_condition: str,
        description: Optional[str] = None,
    ):
        """Initialize join clarification.

        Args:
            tables: List of tables involved in the join
            join_condition: The SQL join condition (e.g., "A.id = B.a_id")
            description: Optional description
        """
        super().__init__(
            correction_type=CorrectionType.JOIN_CLARIFICATION,
            content={
                "tables": tables,
                "join_condition": join_condition,
            },
            description=description,
        )


@dataclass
class ColumnMapping(Correction):
    """Specific correction for column mapping."""

    def __init__(
        self,
        user_term: str,
        actual_column: str,
        description: Optional[str] = None,
    ):
        """Initialize column mapping correction.

        Args:
            user_term: The term used by the user in their query
            actual_column: The actual column name (table.column format)
            description: Optional description
        """
        super().__init__(
            correction_type=CorrectionType.COLUMN_MAPPING,
            content={
                "user_term": user_term,
                "actual_column": actual_column,
            },
            description=description,
        )


@dataclass
class NaturalLanguageCorrection(Correction):
    """Correction provided in natural language."""

    def __init__(self, correction_text: str, description: Optional[str] = None):
        """Initialize natural language correction.

        Args:
            correction_text: The correction in natural language
            description: Optional description
        """
        super().__init__(
            correction_type=CorrectionType.NATURAL_LANGUAGE,
            content={
                "correction": correction_text,
            },
            description=description,
        )


@dataclass
class TableSelectionCorrection(Correction):
    """Specific correction for table selection."""

    def __init__(
        self,
        selected_table: str,
        rejected_tables: Optional[list[str]] = None,
        description: Optional[str] = None,
    ):
        """Initialize table selection correction.

        Args:
            selected_table: The table that should be used
            rejected_tables: Optional list of tables that should NOT be used
            description: Optional description
        """
        super().__init__(
            correction_type=CorrectionType.TABLE_SELECTION,
            content={
                "selected_table": selected_table,
                "rejected_tables": rejected_tables or [],
            },
            description=description,
        )
