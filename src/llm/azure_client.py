"""Azure OpenAI client with retry logic and session management."""

from typing import Optional, Dict, Any, List
from openai import AzureOpenAI, APIError, APITimeoutError, RateLimitError
from ..config import settings
from ..core import Session, session_manager
from ..utils import (
    setup_logger,
    RetryConfig,
    RetryContext,
    RecoverableError,
    FatalError,
    RetryExhaustedError,
)

logger = setup_logger(__name__)


class ResilientAzureOpenAI:
    """Azure OpenAI client with built-in retry logic and session checkpointing."""

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        checkpoint_before_call: bool = True,
    ):
        """Initialize resilient Azure OpenAI client.

        Args:
            retry_config: Retry configuration (uses defaults if None)
            checkpoint_before_call: Whether to checkpoint session before each call
        """
        # Initialize Azure OpenAI client
        azure_config = settings.azure_openai
        self.client = AzureOpenAI(
            api_key=azure_config["api_key"],
            api_version=azure_config["api_version"],
            azure_endpoint=azure_config["endpoint"],
        )

        self.deployment_name = azure_config["deployment_name"]
        self.temperature = azure_config.get("temperature", 0.0)
        self.max_tokens = azure_config.get("max_tokens", 4000)

        # Retry configuration
        self.retry_config = retry_config or RetryConfig.from_settings()
        self.checkpoint_before_call = checkpoint_before_call

        logger.info(
            f"Initialized Azure OpenAI client with deployment: {self.deployment_name}"
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        session: Optional[Session] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Make a chat completion request with retry logic.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            session: Optional session for checkpointing
            temperature: Override default temperature
            max_tokens: Override default max tokens
            **kwargs: Additional arguments for the API call

        Returns:
            Assistant's response content

        Raises:
            RetryExhaustedError: If all retry attempts fail
            FatalError: If a non-retryable error occurs
        """
        # Checkpoint session before call if enabled
        if session and self.checkpoint_before_call:
            session_manager.checkpoint_session(session)

        # Create retry context
        retry_ctx = RetryContext(
            config=self.retry_config,
            operation_name="azure_openai_chat_completion",
        )

        last_exception = None

        while retry_ctx.attempt < retry_ctx.config.max_attempts:
            retry_ctx.increment_attempt()

            try:
                # Log the attempt
                logger.info(
                    f"Azure OpenAI call attempt {retry_ctx.attempt}/"
                    f"{retry_ctx.config.max_attempts}"
                )

                # Make the API call
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=messages,
                    temperature=temperature or self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                    **kwargs,
                )

                # Extract response content
                content = response.choices[0].message.content

                # Update session with response if provided
                if session:
                    session.add_message("assistant", content)
                    session_manager.checkpoint_session(session)

                logger.info("Azure OpenAI call successful")
                return content

            except (APITimeoutError, RateLimitError) as e:
                # These are recoverable errors
                last_exception = RecoverableError(str(e))
                logger.warning(f"Recoverable error: {str(e)}")

                if retry_ctx.should_retry(last_exception):
                    # Update session with retry attempt if provided
                    if session:
                        session.add_message(
                            "system",
                            f"API call failed (attempt {retry_ctx.attempt}): {str(e)}. Retrying...",
                        )
                        session_manager.checkpoint_session(session)

                    retry_ctx.wait()
                else:
                    break

            except APIError as e:
                # Check if this is a retryable error
                if e.status_code and e.status_code >= 500:
                    # Server errors are retryable
                    last_exception = RecoverableError(str(e))
                    logger.warning(f"Server error (retryable): {str(e)}")

                    if retry_ctx.should_retry(last_exception):
                        if session:
                            session.add_message(
                                "system",
                                f"Server error (attempt {retry_ctx.attempt}): {str(e)}. Retrying...",
                            )
                            session_manager.checkpoint_session(session)

                        retry_ctx.wait()
                    else:
                        break
                else:
                    # Client errors (4xx) are not retryable
                    error_msg = f"Azure OpenAI API error (non-retryable): {str(e)}"
                    logger.error(error_msg)

                    if session:
                        session.add_message("system", error_msg)
                        session_manager.checkpoint_session(session)

                    raise FatalError(error_msg) from e

            except Exception as e:
                # Unexpected errors are not retryable
                error_msg = f"Unexpected error in Azure OpenAI call: {str(e)}"
                logger.error(error_msg)

                if session:
                    session.add_message("system", error_msg)
                    session_manager.checkpoint_session(session)

                raise FatalError(error_msg) from e

        # All retries exhausted
        error_msg = (
            f"Azure OpenAI API unavailable after {retry_ctx.config.max_attempts} attempts. "
            f"Last error: {str(last_exception)}"
        )
        logger.error(error_msg)

        # Save session with interrupted state if provided
        if session:
            session.state_machine.transition_to(
                session.state_machine.current_state.__class__.INTERRUPTED,
                reason="API retry exhausted",
            )
            session.add_message("system", error_msg)
            session_manager.save_session(session)

            # Provide recovery instructions
            recovery_msg = self._generate_recovery_message(session)
            logger.info(recovery_msg)

        raise RetryExhaustedError(error_msg) from last_exception

    def _generate_recovery_message(self, session: Session) -> str:
        """Generate recovery instructions for the user.

        Args:
            session: The interrupted session

        Returns:
            Formatted recovery message
        """
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Azure OpenAI API Unavailable
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your session has been saved automatically.

Session ID: {session.session_id}
Status: Interrupted at {session.state_machine.current_state.value}
Reason: Azure API timeout after {self.retry_config.max_attempts} retry attempts

To resume when service is restored:
  > resume {session.session_id}

Your progress has been saved:
✓ Original query: {session.original_query[:50]}...
✓ Iteration: {session.iteration_count}
✓ SQL attempts: {len(session.sql_attempts)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    def generate_structured_output(
        self,
        messages: List[Dict[str, str]],
        session: Optional[Session] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """Generate structured output (e.g., JSON) from the model.

        Args:
            messages: List of message dictionaries
            session: Optional session for checkpointing
            response_format: Response format specification
            **kwargs: Additional arguments

        Returns:
            Assistant's response content
        """
        if response_format:
            kwargs["response_format"] = response_format

        return self.chat_completion(
            messages=messages,
            session=session,
            **kwargs,
        )


# Global resilient Azure OpenAI client instance
azure_client = ResilientAzureOpenAI()
