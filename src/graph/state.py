"""LangGraph state model for text2sql workflow."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class Text2SQLState(BaseModel):
    """State model for LangGraph text2sql workflow.

    This state is passed between all nodes in the graph and contains all
    information needed to orchestrate the query understanding → SQL generation flow.
    """

    # ===== Input/Output =====
    user_query: str
    """The original user query to convert to SQL."""

    final_sql: Optional[str] = None
    """The final generated SQL query (populated on success)."""

    query_results: Optional[Dict[str, Any]] = None
    """Query execution results (if execute_sql=True)."""

    # ===== Session Management =====
    session_id: str
    """Unique identifier for this session/thread."""

    session: Dict[str, Any] = Field(default_factory=dict)
    """Serialized Session object for backward compatibility with existing system."""

    # ===== Workflow Tracking =====
    iteration_count: int = 0
    """Number of workflow iterations (incremented on each retry)."""

    sql_attempt_count: int = 0
    """Number of SQL generation attempts (for retry logic)."""

    # ===== Reasoning Outputs =====
    understanding: Optional[Dict[str, Any]] = None
    """QueryUnderstanding output (tables, columns, joins_needed, etc.)."""

    identified_tables: List[str] = Field(default_factory=list)
    """List of table names identified as relevant for the query."""

    join_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    """List of join candidates from JoinInference (if joins needed)."""

    # ===== Corrections and Constraints =====
    corrections: List[Dict[str, Any]] = Field(default_factory=list)
    """User corrections provided during human-in-the-loop flow."""

    hard_constraints: List[str] = Field(default_factory=list)
    """Constraint strings derived from corrections (passed to LLM prompts)."""

    # ===== SQL Generation Tracking =====
    last_sql: Optional[str] = None
    """The most recently generated SQL (for refinement on retry)."""

    last_error: Optional[str] = None
    """Error message from last SQL validation/execution failure."""

    sql_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    """History of all SQL generation attempts with success/error info."""

    # ===== Error Handling =====
    error: Optional[str] = None
    """General error message (set when workflow encounters failures)."""

    ambiguity_options: Optional[List[str]] = None
    """List of options for user to choose from when ambiguity detected."""

    # ===== Configuration =====
    execute_sql: bool = True
    """Whether to actually execute the SQL (vs just generate)."""

    requires_joins: bool = False
    """Whether the query requires joins between tables."""

    max_sql_attempts: int = 3
    """Maximum number of SQL generation attempts before giving up."""

    # ===== Component References =====
    # Note: Components are passed separately, not in state
    # (They're initialized in the agent and available to nodes via closure)

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True
