"""Pydantic schemas for structured LLM outputs."""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class JoinCandidateOutput(BaseModel):
    """Schema for a single join candidate output from LLM."""

    left_column: str = Field(description="Column name from the left table")
    right_column: str = Field(description="Column name from the right table")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    reasoning: Optional[str] = Field(default=None, description="Explanation for this join")

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1."""
        return max(0.0, min(1.0, v))


class JoinInferenceOutput(BaseModel):
    """Schema for join inference output from LLM."""

    found_joins: bool = Field(description="Whether any joins were found")
    joins: List[JoinCandidateOutput] = Field(
        default_factory=list,
        description="List of join candidates, ordered by confidence"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Overall reasoning for join inference"
    )


class QueryUnderstandingOutput(BaseModel):
    """Schema for query understanding output from LLM."""

    tables: List[str] = Field(
        default_factory=list,
        description="List of table names required for the query"
    )
    columns: List[str] = Field(
        default_factory=list,
        description="List of column names in format 'table.column'"
    )
    joins_needed: bool = Field(
        default=False,
        description="Whether joins between tables are needed"
    )
    filters: Optional[str] = Field(
        default=None,
        description="Description of filter conditions needed"
    )
    aggregations: Optional[str] = Field(
        default=None,
        description="Description of aggregations needed (COUNT, SUM, AVG, etc.)"
    )
    ordering: Optional[str] = Field(
        default=None,
        description="Description of ordering requirements"
    )
    reasoning: str = Field(
        description="Explanation of the query understanding analysis"
    )


class TableRelevanceOutput(BaseModel):
    """Schema for single table relevance evaluation output from LLM."""

    is_relevant: bool = Field(
        description="Whether this table is needed to answer the user query"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the relevance decision (0-1)"
    )

    relevant_columns: List[str] = Field(
        default_factory=list,
        description="Column names from this table needed for the query (if relevant)"
    )

    reasoning: str = Field(
        description="Explanation for why this table is or is not relevant"
    )

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1."""
        return max(0.0, min(1.0, v))


class TableRefinementOutput(BaseModel):
    """Schema for refining selected tables by reviewing them together."""

    final_tables: List[str] = Field(
        description="Final list of table names needed after refinement"
    )

    removed_tables: List[str] = Field(
        default_factory=list,
        description="Tables removed during refinement (if any)"
    )

    reasoning: str = Field(
        description="Explanation for the refinement decisions"
    )


class SQLGenerationOutput(BaseModel):
    """Schema for SQL generation output from LLM."""

    sql: str = Field(
        description="Generated SQL query"
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Explanation of the generated SQL query"
    )
    tables_used: Optional[List[str]] = Field(
        default_factory=list,
        description="List of tables used in the query"
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in the generated SQL (0-1)"
    )
