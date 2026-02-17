"""Data models for database schema representation."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class ColumnType(Enum):
    """Enumeration of supported column types."""
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    TIMESTAMP = "TIMESTAMP"
    NUMERIC = "NUMERIC"
    UNKNOWN = "UNKNOWN"


@dataclass
class Column:
    """Represents a database column with its metadata."""

    name: str
    business_name: Optional[str] = None
    description: Optional[str] = None
    data_type: ColumnType = ColumnType.UNKNOWN
    is_pii: bool = False
    entitlement: Optional[str] = None
    is_mandatory: bool = False
    is_partition: bool = False
    is_primary: bool = False
    table_name: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert column to dictionary representation."""
        return {
            "name": self.name,
            "business_name": self.business_name,
            "description": self.description,
            "data_type": self.data_type.value if self.data_type else None,
            "is_pii": self.is_pii,
            "entitlement": self.entitlement,
            "is_mandatory": self.is_mandatory,
            "is_partition": self.is_partition,
            "is_primary": self.is_primary,
            "table_name": self.table_name,
        }

    def get_full_name(self) -> str:
        """Get fully qualified column name (table.column)."""
        if self.table_name:
            return f"{self.table_name}.{self.name}"
        return self.name


@dataclass
class Table:
    """Represents a database table with its metadata."""

    name: str
    description: Optional[str] = None
    columns: List[Column] = field(default_factory=list)
    business_context: Optional[str] = None
    dataset: Optional[str] = None

    def add_column(self, column: Column) -> None:
        """Add a column to the table."""
        column.table_name = self.name
        self.columns.append(column)

    def get_column(self, column_name: str) -> Optional[Column]:
        """Get a column by name."""
        for col in self.columns:
            if col.name.lower() == column_name.lower():
                return col
        return None

    def get_primary_keys(self) -> List[Column]:
        """Get all primary key columns."""
        return [col for col in self.columns if col.is_primary]

    def to_dict(self) -> Dict:
        """Convert table to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "columns": [col.to_dict() for col in self.columns],
            "business_context": self.business_context,
            "dataset": self.dataset,
        }

    def to_schema_string(self) -> str:
        """Convert table to a human-readable schema string for LLM context."""
        lines = [f"Table: {self.name}"]
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.business_context:
            lines.append(f"Business Context: {self.business_context}")

        lines.append("\nColumns:")
        for col in self.columns:
            col_info = f"  - {col.name} ({col.data_type.value})"
            if col.business_name:
                col_info += f" [Business Name: {col.business_name}]"
            if col.description:
                col_info += f" - {col.description}"
            if col.is_primary:
                col_info += " [PRIMARY KEY]"
            if col.is_pii:
                col_info += " [PII]"
            lines.append(col_info)

        return "\n".join(lines)


@dataclass
class Schema:
    """Represents the complete database schema."""

    tables: Dict[str, Table] = field(default_factory=dict)
    dataset: Optional[str] = None
    project_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def add_table(self, table: Table) -> None:
        """Add a table to the schema."""
        table.dataset = self.dataset
        self.tables[table.name] = table

    def get_table(self, table_name: str) -> Optional[Table]:
        """Get a table by name (case-insensitive)."""
        for name, table in self.tables.items():
            if name.lower() == table_name.lower():
                return table
        return None

    def get_all_columns(self) -> List[Column]:
        """Get all columns across all tables."""
        columns = []
        for table in self.tables.values():
            columns.extend(table.columns)
        return columns

    def to_dict(self) -> Dict:
        """Convert schema to dictionary representation."""
        return {
            "tables": {name: table.to_dict() for name, table in self.tables.items()},
            "dataset": self.dataset,
            "project_id": self.project_id,
            "metadata": self.metadata,
        }

    def to_context_string(self) -> str:
        """Convert schema to a comprehensive string for LLM context.

        This provides all schema information in a format optimized for LLM understanding.
        """
        lines = [
            "=== DATABASE SCHEMA ===",
            f"Project: {self.project_id or 'N/A'}",
            f"Dataset: {self.dataset or 'N/A'}",
            f"Total Tables: {len(self.tables)}",
            "",
        ]

        for table in self.tables.values():
            lines.append(table.to_schema_string())
            lines.append("")  # Blank line between tables

        return "\n".join(lines)


@dataclass
class JoinCandidate:
    """Represents a potential join between two tables."""

    left_table: str
    right_table: str
    left_column: str
    right_column: str
    confidence: float
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert join candidate to dictionary."""
        return {
            "left_table": self.left_table,
            "right_table": self.right_table,
            "left_column": self.left_column,
            "right_column": self.right_column,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }

    def to_sql_condition(self) -> str:
        """Convert to SQL join condition."""
        return f"{self.left_table}.{self.left_column} = {self.right_table}.{self.right_column}"

    def __str__(self) -> str:
        """String representation of join candidate."""
        return (
            f"{self.left_table}.{self.left_column} = "
            f"{self.right_table}.{self.right_column} "
            f"(confidence: {self.confidence:.2f})"
        )
