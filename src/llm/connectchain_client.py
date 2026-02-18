"""ConnectChain client with retry logic and session management.

This module provides a wrapper around AMEX's ConnectChain framework, maintaining
the same interface as the Azure OpenAI client for seamless integration.

For ConnectChain documentation, see: https://github.com/americanexpress/connectchain
"""

import asyncio
from typing import Optional, Dict, Any, List, Type, TypeVar
from pydantic import BaseModel
from connectchain.orchestrators import PortableOrchestrator
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
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

# Type variable for Pydantic models
T = TypeVar('T', bound=BaseModel)


class ResilientConnectChain:
    """ConnectChain client with built-in retry logic and session checkpointing.

    This client wraps AMEX's ConnectChain framework to provide:
    - Enterprise authentication (EAS) support
    - Proxy configuration support
    - Retry logic with exponential backoff
    - Session management and checkpointing
    - Same interface as ResilientAzureOpenAI for easy migration
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        checkpoint_before_call: bool = True,
        model_index: str = '1',
    ):
        """Initialize resilient ConnectChain client.

        Args:
            retry_config: Retry configuration (uses defaults if None)
            checkpoint_before_call: Whether to checkpoint session before each call
            model_index: Index of model configuration in connectchain.config.yml (default: '1')
        """
        self.model_index = model_index

        # Get configuration from settings
        connectchain_config = settings.get("connectchain", {})
        self.temperature = connectchain_config.get("temperature", 0.0)
        self.max_tokens = connectchain_config.get("max_tokens", 4000)

        # Retry configuration - ensure it's a RetryConfig object
        if retry_config is None:
            self.retry_config = RetryConfig.from_settings()
        elif isinstance(retry_config, RetryConfig):
            self.retry_config = retry_config
        else:
            logger.warning(
                f"Invalid retry_config type: {type(retry_config)}. Using default configuration."
            )
            self.retry_config = RetryConfig.from_settings()

        self.checkpoint_before_call = checkpoint_before_call

        logger.info(
            f"Initialized ConnectChain client with model index: {self.model_index}"
        )

    def _create_orchestrator(
        self,
        prompt_template: str,
        input_variables: List[str],
    ) -> PortableOrchestrator:
        """Create a PortableOrchestrator instance.

        Args:
            prompt_template: The prompt template string
            input_variables: List of variable names in the template

        Returns:
            Configured PortableOrchestrator instance
        """
        try:
            orchestrator = PortableOrchestrator.from_prompt_template(
                prompt_template=prompt_template,
                input_variables=input_variables,
                index=self.model_index,
            )
            return orchestrator
        except Exception as e:
            error_msg = f"Failed to create ConnectChain orchestrator: {str(e)}"
            logger.error(error_msg)
            raise FatalError(error_msg) from e

    def _convert_messages_to_prompt(
        self,
        messages: List[Dict[str, str]]
    ) -> str:
        """Convert chat messages to a single prompt string.

        ConnectChain's PortableOrchestrator uses prompt templates rather than
        chat message arrays, so we need to convert the messages format.

        Args:
            messages: List of message dictionaries with 'role' and 'content'

        Returns:
            Formatted prompt string
        """
        prompt_parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}\n")
            elif role == "user":
                prompt_parts.append(f"User: {content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")

        # Add final instruction for the assistant to respond
        prompt_parts.append("Assistant:")

        return "\n".join(prompt_parts)

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        session: Optional[Session] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> str:
        """Make a chat completion request with retry logic.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            session: Optional session for checkpointing
            temperature: Override default temperature (Note: ConnectChain may not support dynamic temperature)
            max_tokens: Override default max tokens (Note: ConnectChain may not support dynamic max_tokens)
            timeout: Optional timeout in seconds for the API call (raises asyncio.TimeoutError if exceeded)
            **kwargs: Additional arguments for the API call

        Returns:
            Assistant's response content

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
            RetryExhaustedError: If all retry attempts fail
            FatalError: If a non-retryable error occurs
        """
        # Checkpoint session before call if enabled
        if session and self.checkpoint_before_call:
            session_manager.checkpoint_session(session)

        # Convert messages to prompt
        prompt_text = self._convert_messages_to_prompt(messages)

        # Create retry context
        retry_ctx = RetryContext(
            config=self.retry_config,
            operation_name="connectchain_chat_completion",
        )

        last_exception = None

        while retry_ctx.attempt < retry_ctx.config.max_attempts:
            retry_ctx.increment_attempt()

            try:
                # Log the attempt
                logger.info(
                    f"ConnectChain call attempt {retry_ctx.attempt}/"
                    f"{retry_ctx.config.max_attempts}"
                )

                # Create orchestrator with the prompt as a template
                # Since we have a complete prompt, we use a simple passthrough template
                orchestrator = self._create_orchestrator(
                    prompt_template="{prompt}",
                    input_variables=["prompt"],
                )

                # Make the API call (run is async, so we need to await it)
                # Use asyncio to run the async function in a synchronous context
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No event loop in current thread, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Wrap with timeout if specified
                if timeout:
                    response = loop.run_until_complete(
                        asyncio.wait_for(orchestrator.run(prompt_text), timeout=timeout)
                    )
                else:
                    response = loop.run_until_complete(orchestrator.run(prompt_text))

                # ConnectChain returns the response directly as a string
                content = response if isinstance(response, str) else str(response)

                # Update session with response if provided
                if session:
                    session.add_message("assistant", content)
                    session_manager.checkpoint_session(session)

                logger.info("ConnectChain call successful")
                return content

            except asyncio.TimeoutError:
                # Timeout occurred - re-raise to caller (used by firewall checker)
                logger.debug(f"Operation timed out after {timeout} seconds")
                raise

            except Exception as e:
                # Analyze the exception to determine if it's retryable
                error_str = str(e).lower()

                # Check for retryable errors (timeout, rate limit, server errors)
                is_retryable = any(
                    keyword in error_str
                    for keyword in ["timeout", "rate limit", "503", "502", "500", "429"]
                )

                if is_retryable:
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
                else:
                    # Non-retryable errors
                    error_msg = f"ConnectChain API error (non-retryable): {str(e)}"
                    logger.error(error_msg)

                    if session:
                        session.add_message("system", error_msg)
                        session_manager.checkpoint_session(session)

                    raise FatalError(error_msg) from e

        # All retries exhausted
        error_msg = (
            f"ConnectChain API unavailable after {retry_ctx.config.max_attempts} attempts. "
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
⚠️  ConnectChain API Unavailable
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your session has been saved automatically.

Session ID: {session.session_id}
Status: Interrupted at {session.state_machine.current_state.value}
Reason: ConnectChain API timeout after {self.retry_config.max_attempts} retry attempts

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
            response_format: Response format specification (Note: may not be fully supported by ConnectChain)
            **kwargs: Additional arguments

        Returns:
            Assistant's response content
        """
        # Note: ConnectChain may not support structured output formats like JSON mode
        # We'll pass the request through and let the prompt guide the format
        if response_format:
            logger.warning(
                "Response format specification may not be fully supported by ConnectChain. "
                "Consider adding format instructions to your prompt."
            )

        return self.chat_completion(
            messages=messages,
            session=session,
            **kwargs,
        )

    def with_structured_output(
        self,
        schema: Type[T],
        messages: List[Dict[str, str]],
        session: Optional[Session] = None,
        **kwargs,
    ) -> T:
        """Use LangChain's with_structured_output() for automatic schema enforcement.

        Args:
            schema: Pydantic model class to enforce
            messages: List of message dictionaries
            session: Optional session for checkpointing
            **kwargs: Additional arguments

        Returns:
            Instance of the Pydantic model with parsed data

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
            operation_name="connectchain_structured_output",
        )

        last_exception = None

        while retry_ctx.attempt < retry_ctx.config.max_attempts:
            retry_ctx.increment_attempt()

            try:
                logger.info(
                    f"ConnectChain structured output call attempt {retry_ctx.attempt}/"
                    f"{retry_ctx.config.max_attempts}"
                )

                # Get LLM directly from ConnectChain using the model function
                try:
                    from connectchain.lcel.model import model as get_model
                    llm = get_model(self.model_index)
                except ImportError:
                    logger.warning("Could not import connectchain.lcel.model, trying alternative")
                    # Fallback: try to access _chain from orchestrator
                    orchestrator = self._create_orchestrator(
                        prompt_template="{prompt}",
                        input_variables=["prompt"],
                    )
                    # Access the private _chain attribute (not ideal but necessary)
                    if hasattr(orchestrator, '_chain'):
                        chain = orchestrator._chain
                        if hasattr(chain, 'llm'):
                            llm = chain.llm
                        else:
                            raise FatalError("Cannot access LLM from ConnectChain orchestrator")
                    else:
                        raise FatalError("Cannot access chain from ConnectChain orchestrator")

                # Wrap LLM with structured output
                structured_llm = llm.with_structured_output(schema)

                # Convert messages to LangChain format
                lc_messages = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")

                    if role == "system":
                        lc_messages.append(SystemMessage(content=content))
                    else:  # user or assistant
                        lc_messages.append(HumanMessage(content=content))

                # Run with structured output
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Invoke the structured LLM
                result = loop.run_until_complete(structured_llm.ainvoke(lc_messages))

                # Update session with response if provided
                if session:
                    session.add_message("assistant", str(result))
                    session_manager.checkpoint_session(session)

                logger.info("ConnectChain structured output call successful")
                return result

            except asyncio.TimeoutError:
                logger.debug("Operation timed out")
                raise

            except Exception as e:
                # Analyze the exception to determine if it's retryable
                error_str = str(e).lower()

                # Check for retryable errors
                is_retryable = any(
                    keyword in error_str
                    for keyword in ["timeout", "rate limit", "503", "502", "500", "429"]
                )

                if is_retryable:
                    last_exception = RecoverableError(str(e))
                    logger.warning(f"Recoverable error: {str(e)}")

                    if retry_ctx.should_retry(last_exception):
                        if session:
                            session.add_message(
                                "system",
                                f"API call failed (attempt {retry_ctx.attempt}): {str(e)}. Retrying...",
                            )
                            session_manager.checkpoint_session(session)

                        retry_ctx.wait()
                    else:
                        break
                else:
                    # Non-retryable errors
                    error_msg = f"ConnectChain structured output error (non-retryable): {str(e)}"
                    logger.error(error_msg)

                    if session:
                        session.add_message("system", error_msg)
                        session_manager.checkpoint_session(session)

                    raise FatalError(error_msg) from e

        # All retries exhausted
        error_msg = (
            f"ConnectChain API unavailable after {retry_ctx.config.max_attempts} attempts. "
            f"Last error: {str(last_exception)}"
        )
        logger.error(error_msg)

        if session:
            session.state_machine.transition_to(
                session.state_machine.current_state.__class__.INTERRUPTED,
                reason="API retry exhausted",
            )
            session.add_message("system", error_msg)
            session_manager.save_session(session)

        raise RetryExhaustedError(error_msg) from last_exception


# Global resilient ConnectChain client instance
# Note: This will use the default model index '1' from connectchain.config.yml
connectchain_client = ResilientConnectChain()
