"""State machine for agent execution flow."""

from enum import Enum
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


class AgentState(Enum):
    """Enumeration of agent execution states."""

    INITIALIZING = "initializing"
    SCHEMA_LOADING = "schema_loading"
    QUERY_UNDERSTANDING = "query_understanding"
    JOIN_INFERENCE = "join_inference"
    EXECUTING_EXPLORATION = "executing_exploration"
    GENERATING_SQL = "generating_sql"
    EXECUTING_QUERY = "executing_query"
    AWAITING_CORRECTION = "awaiting_correction"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class StateTransition:
    """Represents a state transition in the agent execution."""

    from_state: AgentState
    to_state: AgentState
    timestamp: datetime
    reason: Optional[str] = None
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert state transition to dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metadata": self.metadata or {},
        }


class AgentStateMachine:
    """Manages agent state transitions and validates state changes."""

    # Define valid state transitions
    VALID_TRANSITIONS = {
        AgentState.INITIALIZING: {
            AgentState.SCHEMA_LOADING,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.SCHEMA_LOADING: {
            AgentState.QUERY_UNDERSTANDING,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.QUERY_UNDERSTANDING: {
            AgentState.JOIN_INFERENCE,
            AgentState.EXECUTING_EXPLORATION,
            AgentState.GENERATING_SQL,
            AgentState.AWAITING_CORRECTION,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.JOIN_INFERENCE: {
            AgentState.EXECUTING_EXPLORATION,
            AgentState.GENERATING_SQL,
            AgentState.AWAITING_CORRECTION,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.EXECUTING_EXPLORATION: {
            AgentState.JOIN_INFERENCE,
            AgentState.GENERATING_SQL,
            AgentState.AWAITING_CORRECTION,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.GENERATING_SQL: {
            AgentState.EXECUTING_QUERY,
            AgentState.AWAITING_CORRECTION,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.EXECUTING_QUERY: {
            AgentState.COMPLETED,
            AgentState.GENERATING_SQL,
            AgentState.AWAITING_CORRECTION,
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.AWAITING_CORRECTION: {
            AgentState.QUERY_UNDERSTANDING,  # Restart with corrections
            AgentState.FAILED,
            AgentState.INTERRUPTED,
        },
        AgentState.COMPLETED: set(),  # Terminal state
        AgentState.FAILED: set(),  # Terminal state
        AgentState.INTERRUPTED: {
            # Can resume from interrupted state to any previous state
            AgentState.SCHEMA_LOADING,
            AgentState.QUERY_UNDERSTANDING,
            AgentState.JOIN_INFERENCE,
            AgentState.EXECUTING_EXPLORATION,
            AgentState.GENERATING_SQL,
            AgentState.EXECUTING_QUERY,
        },
    }

    def __init__(self, initial_state: AgentState = AgentState.INITIALIZING):
        """Initialize state machine with initial state."""
        self.current_state = initial_state
        self.transitions: list[StateTransition] = []

    def can_transition_to(self, target_state: AgentState) -> bool:
        """Check if transition to target state is valid."""
        valid_targets = self.VALID_TRANSITIONS.get(self.current_state, set())
        return target_state in valid_targets

    def transition_to(
        self,
        target_state: AgentState,
        reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Transition to a new state.

        Args:
            target_state: The state to transition to
            reason: Optional reason for the transition
            metadata: Optional metadata about the transition

        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_transition_to(target_state):
            raise ValueError(
                f"Invalid state transition from {self.current_state.value} "
                f"to {target_state.value}"
            )

        transition = StateTransition(
            from_state=self.current_state,
            to_state=target_state,
            timestamp=datetime.now(),
            reason=reason,
            metadata=metadata,
        )

        self.transitions.append(transition)
        self.current_state = target_state

    def is_terminal_state(self) -> bool:
        """Check if current state is terminal (completed, failed)."""
        return self.current_state in {
            AgentState.COMPLETED,
            AgentState.FAILED,
        }

    def is_awaiting_input(self) -> bool:
        """Check if agent is awaiting user input."""
        return self.current_state in {
            AgentState.AWAITING_CORRECTION,
            AgentState.INTERRUPTED,
        }

    def get_transition_history(self) -> list[dict]:
        """Get history of all state transitions."""
        return [t.to_dict() for t in self.transitions]

    def to_dict(self) -> dict:
        """Convert state machine to dictionary."""
        return {
            "current_state": self.current_state.value,
            "transitions": self.get_transition_history(),
            "is_terminal": self.is_terminal_state(),
            "is_awaiting_input": self.is_awaiting_input(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AgentStateMachine':
        """Restore state machine from dictionary."""
        current_state = AgentState(data["current_state"])
        state_machine = cls(initial_state=current_state)

        # Restore transition history
        state_machine.transitions = [
            StateTransition(
                from_state=AgentState(t["from_state"]),
                to_state=AgentState(t["to_state"]),
                timestamp=datetime.fromisoformat(t["timestamp"]),
                reason=t.get("reason"),
                metadata=t.get("metadata"),
            )
            for t in data.get("transitions", [])
        ]

        return state_machine
