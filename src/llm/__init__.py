"""LLM interaction modules.

This module provides LLM clients for both direct Azure OpenAI access and
ConnectChain (AMEX's enterprise AI framework).

The default client can be selected via configuration.
"""

from ..config import settings
from .azure_client import ResilientAzureOpenAI, azure_client
from .connectchain_client import ResilientConnectChain, connectchain_client
from .prompts import PromptTemplates


def get_llm_client():
    """Get the configured LLM client based on settings.

    Returns:
        Either ResilientAzureOpenAI or ResilientConnectChain instance

    Usage:
        llm_client = get_llm_client()
        response = llm_client.chat_completion(messages)
    """
    # Check if ConnectChain is enabled in configuration
    use_connectchain = settings.get("llm.use_connectchain", False)

    if use_connectchain:
        return connectchain_client
    else:
        return azure_client


# Default LLM client - automatically selects based on configuration
llm_client = get_llm_client()

__all__ = [
    # Azure OpenAI
    "ResilientAzureOpenAI",
    "azure_client",
    # ConnectChain
    "ResilientConnectChain",
    "connectchain_client",
    # Auto-selector
    "get_llm_client",
    "llm_client",
    # Prompts
    "PromptTemplates",
]
