"""Text-to-SQL Agent: A production-ready system for converting natural language to SQL queries.

This package provides a comprehensive solution for text-to-SQL conversion with:
- ConnectChain (AMEX enterprise AI framework) integration with retry logic
- BigQuery database support
- Semantic join inference without explicit foreign keys
- Session management with persistence
- Human-in-the-loop corrections
- Multi-step reasoning with exploration queries
"""

# Load environment variables at package import
import os
from pathlib import Path
from dotenv import load_dotenv

# Find and load .env file from project root
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
    # Set proxy environment variables if defined
    if os.getenv("HTTP_PROXY"):
        os.environ["HTTP_PROXY"] = os.getenv("HTTP_PROXY")
    if os.getenv("HTTPS_PROXY"):
        os.environ["HTTPS_PROXY"] = os.getenv("HTTPS_PROXY")

__version__ = "1.0.0"
__author__ = "AMEX Data Engineering Team"

from .config import settings
from .core import Session, SessionManager, session_manager, AgentState
from .schema import Schema, Table, Column, schema_loader
from .database import BigQueryClient, bigquery_client
from .llm import llm_client, connectchain_client
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
    # LLM (ConnectChain - enterprise requirement)
    "llm_client",
    "connectchain_client",
    # Correction
    "CorrectionParser",
    # Reasoning
    "JoinInference",
    # Agent
    "Text2SQLAgent",
]
