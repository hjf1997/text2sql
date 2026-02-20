"""Session management with file-based persistence."""

import json
import uuid
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from .state_machine import AgentStateMachine, AgentState
from ..correction.models import Correction
from ..config import settings
from ..utils import SessionError, setup_logger

logger = setup_logger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime, date, time, and timedelta objects."""

    def default(self, obj):
        """Convert datetime-related objects to ISO format strings."""
        if isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return obj.total_seconds()
        return super().default(obj)


class Session:
    """Represents an agent execution session with full state tracking."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        user_query: Optional[str] = None,
    ):
        """Initialize a new session.

        Args:
            session_id: Optional session ID (generates new if None)
            user_query: The user's original query
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.created_at = datetime.now()
        self.last_updated = datetime.now()

        # Query context
        self.original_query = user_query
        self.schema_snapshot: Optional[Dict] = None

        # Conversation history
        self.messages: List[Dict[str, Any]] = []

        # State machine
        self.state_machine = AgentStateMachine()

        # Reasoning state
        self.iteration_count = 0
        self.correction_attempt = 0

        # Agent memory
        self.identified_tables: List[str] = []
        self.inferred_joins: List[Dict] = []
        self.intermediate_results: Dict[str, Any] = {}

        # Corrections and constraints
        self.corrections: List[Correction] = []
        self.hard_constraints: List[str] = []

        # Execution history
        self.sql_attempts: List[Dict[str, Any]] = []

        # Failure summary (if failed)
        self.failure_summary: Optional[Dict[str, Any]] = None

    @property
    def status(self) -> str:
        """Get current session status."""
        if self.state_machine.current_state == AgentState.COMPLETED:
            return "completed"
        elif self.state_machine.current_state == AgentState.FAILED:
            return "failed"
        elif self.state_machine.current_state == AgentState.INTERRUPTED:
            return "interrupted"
        elif self.state_machine.current_state == AgentState.AWAITING_CORRECTION:
            return "awaiting_correction"
        return "active"

    @property
    def final_sql(self) -> Optional[str]:
        """Get the final successful SQL query from attempts.

        Returns:
            The SQL from the last successful attempt, or None if no successful attempts
        """
        if not self.sql_attempts:
            return None

        # Return the last successful SQL attempt
        for attempt in reversed(self.sql_attempts):
            if attempt.get("success"):
                return attempt.get("sql")

        return None

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add a message to conversation history.

        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            metadata: Optional metadata
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self.messages.append(message)
        self.last_updated = datetime.now()

    def add_sql_attempt(
        self,
        sql: str,
        success: bool,
        error: Optional[str] = None,
        results: Optional[Any] = None,
    ) -> None:
        """Record a SQL execution attempt.

        Args:
            sql: The SQL query
            success: Whether execution succeeded
            error: Error message if failed
            results: Query results if successful
        """
        attempt = {
            "sql": sql,
            "success": success,
            "error": error,
            "results": results,
            "timestamp": datetime.now().isoformat(),
            "iteration": self.iteration_count,
        }
        self.sql_attempts.append(attempt)
        self.last_updated = datetime.now()

    def add_correction(self, correction: Correction) -> None:
        """Add a user correction.

        Args:
            correction: Correction object
        """
        correction.attempt_number = self.correction_attempt
        self.corrections.append(correction)

        # Convert correction to constraint string
        constraint = correction.to_constraint_string()
        if constraint:
            self.hard_constraints.append(constraint)

        self.last_updated = datetime.now()
        logger.info(f"Added correction to session {self.session_id}: {constraint}")

    def add_intermediate_result(self, key: str, value: Any) -> None:
        """Store intermediate result.

        Args:
            key: Result identifier
            value: Result value
        """
        self.intermediate_results[key] = {
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }
        self.last_updated = datetime.now()

    def increment_iteration(self) -> None:
        """Increment iteration counter."""
        self.iteration_count += 1
        self.last_updated = datetime.now()

    def increment_correction_attempt(self) -> None:
        """Increment correction attempt counter."""
        self.correction_attempt += 1
        self.last_updated = datetime.now()

    def set_failure_summary(self, summary: Dict[str, Any]) -> None:
        """Set failure summary.

        Args:
            summary: Failure summary dictionary
        """
        self.failure_summary = summary
        self.last_updated = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "original_query": self.original_query,
            "schema_snapshot": self.schema_snapshot,
            "messages": self.messages,
            "state_machine": self.state_machine.to_dict(),
            "iteration_count": self.iteration_count,
            "correction_attempt": self.correction_attempt,
            "identified_tables": self.identified_tables,
            "inferred_joins": self.inferred_joins,
            "intermediate_results": self.intermediate_results,
            "corrections": [c.to_dict() for c in self.corrections],
            "hard_constraints": self.hard_constraints,
            "sql_attempts": self.sql_attempts,
            "failure_summary": self.failure_summary,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Restore session from dictionary.

        Args:
            data: Session data dictionary

        Returns:
            Restored Session object
        """
        session = cls(
            session_id=data["session_id"],
            user_query=data.get("original_query"),
        )

        session.created_at = datetime.fromisoformat(data["created_at"])
        session.last_updated = datetime.fromisoformat(data["last_updated"])
        session.schema_snapshot = data.get("schema_snapshot")
        session.messages = data.get("messages", [])
        session.iteration_count = data.get("iteration_count", 0)
        session.correction_attempt = data.get("correction_attempt", 0)
        session.identified_tables = data.get("identified_tables", [])
        session.inferred_joins = data.get("inferred_joins", [])
        session.intermediate_results = data.get("intermediate_results", {})
        session.hard_constraints = data.get("hard_constraints", [])
        session.sql_attempts = data.get("sql_attempts", [])
        session.failure_summary = data.get("failure_summary")

        # Restore state machine
        if "state_machine" in data:
            session.state_machine = AgentStateMachine.from_dict(data["state_machine"])

        # Restore corrections
        for corr_data in data.get("corrections", []):
            correction = Correction.from_dict(corr_data)
            session.corrections.append(correction)

        return session


class SessionManager:
    """Manages session persistence and lifecycle."""

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize session manager.

        Args:
            storage_path: Directory for storing session files
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path(settings.get("session.storage.base_path", "sessions"))

        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session manager initialized with storage: {self.storage_path}")

    def create_session(self, user_query: str) -> Session:
        """Create a new session.

        Args:
            user_query: The user's query

        Returns:
            New Session object
        """
        session = Session(user_query=user_query)
        self.save_session(session)
        logger.info(f"Created new session: {session.session_id}")
        return session

    def save_session(self, session: Session) -> None:
        """Save session to storage.

        Args:
            session: Session to save

        Raises:
            SessionError: If save fails
        """
        try:
            session_file = self._get_session_file(session.session_id)
            with open(session_file, 'w') as f:
                json.dump(session.to_dict(), f, indent=2, cls=DateTimeEncoder)

            logger.debug(f"Saved session {session.session_id}")

        except Exception as e:
            raise SessionError(f"Failed to save session: {str(e)}") from e

    def load_session(self, session_id: str) -> Session:
        """Load session from storage.

        Args:
            session_id: Session ID to load

        Returns:
            Loaded Session object

        Raises:
            SessionError: If session not found or load fails
        """
        session_file = self._get_session_file(session_id)

        if not session_file.exists():
            raise SessionError(f"Session not found: {session_id}")

        try:
            with open(session_file, 'r') as f:
                data = json.load(f)

            session = Session.from_dict(data)
            logger.info(f"Loaded session {session_id}")
            return session

        except Exception as e:
            raise SessionError(f"Failed to load session: {str(e)}") from e

    def checkpoint_session(self, session: Session) -> None:
        """Save session checkpoint (same as save, but semantically different).

        Args:
            session: Session to checkpoint
        """
        self.save_session(session)
        logger.debug(f"Checkpointed session {session.session_id}")

    def delete_session(self, session_id: str) -> None:
        """Delete a session.

        Args:
            session_id: Session ID to delete

        Raises:
            SessionError: If deletion fails
        """
        session_file = self._get_session_file(session_id)

        if not session_file.exists():
            logger.warning(f"Session {session_id} not found for deletion")
            return

        try:
            session_file.unlink()
            logger.info(f"Deleted session {session_id}")

        except Exception as e:
            raise SessionError(f"Failed to delete session: {str(e)}") from e

    def list_sessions(
        self,
        status_filter: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """List available sessions.

        Args:
            status_filter: Optional status filter (active, completed, failed, etc.)
            limit: Maximum number of sessions to return

        Returns:
            List of session summaries
        """
        sessions = []

        for session_file in sorted(
            self.storage_path.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)

                # Apply status filter
                if status_filter and data.get("status") != status_filter:
                    continue

                sessions.append({
                    "session_id": data["session_id"],
                    "created_at": data["created_at"],
                    "last_updated": data["last_updated"],
                    "query": data.get("original_query"),
                    "status": data.get("status"),
                })

                if len(sessions) >= limit:
                    break

            except Exception as e:
                logger.warning(f"Error reading session file {session_file}: {str(e)}")
                continue

        return sessions

    def cleanup_old_sessions(self) -> int:
        """Clean up old sessions based on retention policy.

        Returns:
            Number of sessions deleted
        """
        retention_days = {
            "completed": settings.get("session.retention.completed_sessions", 30),
            "failed": settings.get("session.retention.failed_sessions", 90),
        }

        deleted_count = 0

        for session_file in self.storage_path.glob("*.json"):
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)

                status = data.get("status", "active")
                last_updated = datetime.fromisoformat(data["last_updated"])

                # Determine retention period
                if status in retention_days:
                    retention = retention_days[status]
                    cutoff = datetime.now() - timedelta(days=retention)

                    if last_updated < cutoff:
                        session_file.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old session: {data['session_id']}")

            except Exception as e:
                logger.warning(f"Error processing session file {session_file}: {str(e)}")
                continue

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old sessions")

        return deleted_count

    def _get_session_file(self, session_id: str) -> Path:
        """Get file path for a session.

        Args:
            session_id: Session ID

        Returns:
            Path to session file
        """
        return self.storage_path / f"{session_id}.json"


# Global session manager instance
session_manager = SessionManager()
