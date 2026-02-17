"""LLM interaction modules.

This module provides LLM client through ConnectChain (AMEX's enterprise AI framework).

ConnectChain is required for all LLM interactions in the enterprise environment.
"""

from .connectchain_client import ResilientConnectChain, connectchain_client
from .prompts import PromptTemplates


# Default LLM client - uses ConnectChain (enterprise requirement)
llm_client = connectchain_client

__all__ = [
    # ConnectChain (enterprise LLM client)
    "ResilientConnectChain",
    "connectchain_client",
    "llm_client",
    # Prompts
    "PromptTemplates",
]
