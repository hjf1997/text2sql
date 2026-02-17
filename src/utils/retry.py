"""Retry logic with exponential backoff for API calls."""

import time
import random
from typing import Callable, Any, Type, Tuple, Optional
from functools import wraps
from ..config import settings
from .logger import setup_logger
from .exceptions import RecoverableError, FatalError, RetryExhaustedError

logger = setup_logger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (RecoverableError,),
        fatal_exceptions: Tuple[Type[Exception], ...] = (FatalError,),
    ):
        """Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            multiplier: Multiplier for exponential backoff
            jitter: Whether to add random jitter to delays
            retryable_exceptions: Exceptions that should trigger retry
            fatal_exceptions: Exceptions that should not be retried
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions
        self.fatal_exceptions = fatal_exceptions

    @classmethod
    def from_settings(cls, section: str = "connectchain.retry") -> 'RetryConfig':
        """Create retry config from settings.

        Args:
            section: Configuration section path

        Returns:
            RetryConfig instance
        """
        # Get values with type conversion to ensure correct types
        max_attempts = settings.get(f"{section}.max_attempts", 5)
        base_delay = settings.get(f"{section}.base_delay", 2.0)
        max_delay = settings.get(f"{section}.max_delay", 60.0)
        multiplier = settings.get(f"{section}.multiplier", 2.0)
        jitter = settings.get(f"{section}.jitter", True)

        # Convert to proper types (in case YAML loads them as strings)
        try:
            max_attempts = int(max_attempts)
            base_delay = float(base_delay)
            max_delay = float(max_delay)
            multiplier = float(multiplier)
            jitter = bool(jitter) if not isinstance(jitter, bool) else jitter
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert retry config values: {e}. Using defaults.")
            max_attempts = 5
            base_delay = 2.0
            max_delay = 60.0
            multiplier = 2.0
            jitter = True

        return cls(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            multiplier=multiplier,
            jitter=jitter,
        )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Calculate exponential backoff
        delay = min(
            self.base_delay * (self.multiplier ** attempt),
            self.max_delay,
        )

        # Add jitter if enabled
        if self.jitter:
            # Add random jitter of ±25%
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0, delay)  # Ensure non-negative

        return delay


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """Decorator to retry a function with exponential backoff.

    Args:
        config: Retry configuration (uses default if None)
        on_retry: Optional callback called before each retry with (exception, attempt_number)

    Returns:
        Decorated function

    Example:
        @retry_with_backoff()
        def my_api_call():
            # Make API call
            pass
    """
    if config is None:
        config = RetryConfig.from_settings()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except config.fatal_exceptions as e:
                    # Don't retry fatal exceptions
                    logger.error(
                        f"Fatal error in {func.__name__}: {str(e)}. "
                        f"Not retrying."
                    )
                    raise

                except config.retryable_exceptions as e:
                    last_exception = e
                    remaining_attempts = config.max_attempts - attempt - 1

                    if remaining_attempts == 0:
                        # No more retries left
                        logger.error(
                            f"All {config.max_attempts} retry attempts exhausted "
                            f"for {func.__name__}"
                        )
                        raise RetryExhaustedError(
                            f"Failed after {config.max_attempts} attempts: {str(e)}"
                        ) from e

                    # Calculate delay and log
                    delay = config.calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{config.max_attempts} failed "
                        f"for {func.__name__}: {str(e)}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    # Call on_retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt + 1)
                        except Exception as callback_error:
                            logger.error(
                                f"Error in retry callback: {str(callback_error)}"
                            )

                    # Wait before retrying
                    time.sleep(delay)

                except Exception as e:
                    # Unexpected exception - don't retry
                    logger.error(
                        f"Unexpected error in {func.__name__}: {type(e).__name__}: {str(e)}. "
                        f"Not retrying."
                    )
                    raise

            # This should not be reached, but just in case
            if last_exception:
                raise RetryExhaustedError(
                    f"Failed after {config.max_attempts} attempts"
                ) from last_exception
            raise RuntimeError("Retry loop exited unexpectedly")

        return wrapper

    return decorator


class RetryContext:
    """Context manager for retry operations with custom tracking.

    This is useful when you need more control over the retry logic,
    such as saving state between retries.
    """

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        operation_name: str = "operation",
    ):
        """Initialize retry context.

        Args:
            config: Retry configuration
            operation_name: Name of the operation for logging
        """
        # Ensure config is a RetryConfig object, not a string or other type
        if config is None:
            self.config = RetryConfig.from_settings()
        elif isinstance(config, RetryConfig):
            self.config = config
        else:
            # If config is not the right type, log warning and use defaults
            logger.warning(
                f"Invalid retry config type: {type(config)}. Using default configuration."
            )
            self.config = RetryConfig.from_settings()

        self.operation_name = operation_name
        self.attempt = 0
        self.last_exception: Optional[Exception] = None

    def should_retry(self, exception: Exception) -> bool:
        """Check if operation should be retried.

        Args:
            exception: The exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        self.last_exception = exception

        # Don't retry fatal exceptions
        if isinstance(exception, self.config.fatal_exceptions):
            logger.error(
                f"Fatal error in {self.operation_name}: {str(exception)}"
            )
            return False

        # Check if we have attempts left
        if self.attempt >= self.config.max_attempts:
            logger.error(
                f"Max attempts ({self.config.max_attempts}) reached "
                f"for {self.operation_name}"
            )
            return False

        # Retry on recoverable exceptions
        if isinstance(exception, self.config.retryable_exceptions):
            return True

        # Don't retry other exceptions
        logger.error(
            f"Non-retryable error in {self.operation_name}: "
            f"{type(exception).__name__}: {str(exception)}"
        )
        return False

    def wait(self) -> None:
        """Wait before next retry attempt."""
        delay = self.config.calculate_delay(self.attempt)
        remaining = self.config.max_attempts - self.attempt
        logger.warning(
            f"Attempt {self.attempt}/{self.config.max_attempts} failed "
            f"for {self.operation_name}. "
            f"Retrying in {delay:.2f}s... ({remaining} attempts remaining)"
        )
        time.sleep(delay)

    def increment_attempt(self) -> None:
        """Increment attempt counter."""
        self.attempt += 1
