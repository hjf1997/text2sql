"""Component registry for LangGraph nodes.

This module provides a thread-safe way for nodes to access
initialized components (QueryUnderstanding, JoinInference, etc.)
from the agent.
"""

import threading
from typing import Dict, Any, Optional

_component_registry: Dict[str, Dict[str, Any]] = {}
_registry_lock = threading.Lock()


def register_components(thread_id: str, components: Dict[str, Any]) -> None:
    """Register components for a specific thread/session.

    Args:
        thread_id: Session/thread identifier
        components: Dictionary of component name -> component instance
    """
    with _registry_lock:
        _component_registry[thread_id] = components


def get_components(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get registered components for a thread/session.

    Args:
        thread_id: Session/thread identifier

    Returns:
        Dictionary of components, or None if not found
    """
    with _registry_lock:
        return _component_registry.get(thread_id)


def unregister_components(thread_id: str) -> None:
    """Unregister components for a thread/session.

    Args:
        thread_id: Session/thread identifier
    """
    with _registry_lock:
        _component_registry.pop(thread_id, None)


def clear_all_components() -> None:
    """Clear all registered components (for testing)."""
    with _registry_lock:
        _component_registry.clear()
