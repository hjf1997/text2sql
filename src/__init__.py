"""Text-to-SQL Agent: A production-ready system for converting natural language to SQL queries.

This package provides a comprehensive solution for text-to-SQL conversion with:
- Azure OpenAI integration with retry logic
- BigQuery database support
- Semantic join inference without explicit foreign keys
- Session management with persistence
- Human-in-the-loop corrections
- Multi-step reasoning with exploration queries
"""

__version__ = "1.0.0"
__author__ = "AMEX Data Engineering Team"

from .config import settings
from .core import Session, SessionManager, session_manager, AgentState
from .schema import Schema, Table, Column, schema_loader
from .database import BigQueryClient, bigquery_client
from .llm import azure_client
from .correction import CorrectionParser
from .reasoning import JoinInference
from .agent import Text2SQLAgent

__all__ = [
    # Version
    "__version__",
    # Config
    "settings",
    # Core
    "Session",
    "SessionManager",
    "session_manager",
    "AgentState",
    # Schema
    "Schema",
    "Table",
    "Column",
    "schema_loader",
    # Database
    "BigQueryClient",
    "bigquery_client",
    # LLM
    "azure_client",
    # Correction
    "CorrectionParser",
    # Reasoning
    "JoinInference",
    # Agent
    "Text2SQLAgent",
]
