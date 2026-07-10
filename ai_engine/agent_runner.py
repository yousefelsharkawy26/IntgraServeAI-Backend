# ai_engine/agent_runner.py

import asyncio
import inspect
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage

from .action_engine import ActionEngine
from .providers import ModelFactory
from .vector_search import (
    EmbeddingProviderError, OllamaConnectionError, OllamaModelError,
    ProviderAuthenticationError, ProviderTimeoutError
)
from utils.exceptions import (
    ActionRequiresConfirmationError, ParsingException, ExecutionException,
    EmbeddingGenerationError, CorrelationIdAdapter, get_correlation_id, set_correlation_id,
)

logger = CorrelationIdAdapter(logging.getLogger(__name__))


class AgentRunner:
    def __init__(self, action_engine: ActionEngine, internal_handler=None):
        self.engine = action_engine
        self.internal_handler = internal_handler

        self.tools = self.engine.build_tools()

        if not self.engine.agent_config.llm_config:
            raise ParsingException(
                "llm_config is required in agent configuration but was not provided. "
                "Please define 'llm_config' in your agent_config.json with at least "
                "'provider' and 'model_name' fields."
            )

        self.llm = ModelFactory.get_llm(self.engine.agent_config.llm_config)

        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm

        self.system_prompt = self.engine.get_system_prompt()

    # P5.2: Reload tools from the action engine at runtime
    def reload_tools(self) -> None:
        """Reload tools from the action engine.
        
        Call this method if the engine's configuration has been reloaded at runtime
        (e.g., actions were added, removed, or updated). Rebuilds the tool list
        and rebinds them to the LLM.
        """
        self.tools = self.engine.build_tools()
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm
        logger.info(f"Reloaded {len(self.tools)} tools from action engine.")

    def _to_ai_message(self, ai_message_chunk: BaseMessage) -> AIMessage:
        """Convert a streamed AIMessageChunk into a stable AIMessage for history.

        Chat model history should contain full message objects, not streaming
        chunks. Keeping AIMessageChunk in working_messages can make the next
        provider invocation fail when LangChain serializes the transcript after
        tool execution.
        """
        return AIMessage(
            content=getattr(ai_message_chunk, "content", "") or "",
            additional_kwargs=getattr(ai_message_chunk, "additional_kwargs", {}) or {},
            response_metadata=getattr(ai_message_chunk, "response_metadata", {}) or {},
            tool_calls=getattr(ai_message_chunk, "tool_calls", []) or [],
            invalid_tool_calls=getattr(ai_message_chunk, "invalid_tool_calls", []) or [],
            usage_metadata=getattr(ai_message_chunk, "usage_metadata", None),
            id=getattr(ai_message_chunk, "id", None),
            name=getattr(ai_message_chunk, "name", None),
        )

    def _log_ai_message_chunk(self, ai_message_chunk: BaseMessage) -> None:
        logger.info("AgentRunner ai_message_chunk type=%s", type(ai_message_chunk))
        logger.info("AgentRunner ai_message_chunk repr=%r", ai_message_chunk)

    def _log_working_messages(self, working_messages: List[BaseMessage], iteration_count: int) -> None:
        logger.info(
            "AgentRunner invoking LLM iteration=%s message_count=%s",
            iteration_count,
            len(working_messages),
        )
        for index, message in enumerate(working_messages):
            content = getattr(message, "content", None)
            logger.info(
                "AgentRunner message[%s] type=%s class=%s content_type=%s content_repr=%r",
                index,
                getattr(message, "type", None),
                message.__class__.__name__,
                type(content),
                content,
            )

    def _make_tool_message(self, tool_id: str, result: Any) -> ToolMessage:
        result_str = result if isinstance(result, str) else str(result)
        tool_message = ToolMessage(content=result_str, tool_call_id=tool_id)
        logger.info("AgentRunner tool result type=%s repr=%r", type(result), result)
        logger.info("AgentRunner tool result_str type=%s repr=%r", type(result_str), result_str)
        logger.info("AgentRunner ToolMessage repr=%r", tool_message)
        return tool_message

    async def stream_chat(
        self,
        messages: List[BaseMessage],
        correlation_id: Optional[str] = None,
        cancel_token: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams the AI's response token-by-token.
        Automatically handles tool execution and pauses for user confirmation.

        Args:
            messages: Conversation history as LangChain message objects.
            correlation_id: Optional correlation ID for structured logging and
                event tracing across the async execution context.

        Yields:
            Dict with keys:
                - "type": "token" | "done" | "tool_start" | "tool_end" | "tool_error" | "pause"
                - "correlation_id": The correlation ID for this execution context
                - Additional keys depending on type

        Resume state (for "pause" events):
            The pause event includes a "_resume_state" key containing the assistant
            message and completed tool results. The caller must reconstruct the
            conversation history and call stream_chat again.
        """
        # P5.1: Set correlation ID in the async context for structured logging
        token = None
        if correlation_id:
            token = set_correlation_id(correlation_id)
        
        try:
            working_messages = list(messages)

            if not working_messages or not isinstance(working_messages[0], SystemMessage):
                working_messages.insert(0, SystemMessage(content=self.system_prompt))

            rate_limit_delay = 0
            max_iterations = 20
            if self.engine.agent_config.llm_config:
                rate_limit_delay = self.engine.agent_config.llm_config.rate_limit_delay_seconds or 0
                max_iterations = self.engine.agent_config.llm_config.max_iterations or 20

            first_iteration = True
            iteration_count = 0

            while True:
                iteration_count += 1
                if iteration_count > max_iterations:
                    error_message = (
                        f"Maximum agent iterations exceeded ({max_iterations}). "
                        "Stopping to prevent a runaway tool-calling loop."
                    )
                    logger.error(error_message)
                    yield {
                        "type": "error",
                        "message": error_message,
                        "correlation_id": get_correlation_id(),
                    }
                    break
                if not first_iteration and rate_limit_delay > 0:
                    logger.info(
                        f"Rate Limiter: Sleeping for {rate_limit_delay}s to respect API quotas..."
                    )
                    await asyncio.sleep(rate_limit_delay)
                first_iteration = False

                ai_message_chunk = None

                self._log_working_messages(working_messages, iteration_count)

                async for chunk in self.llm_with_tools.astream(working_messages):
                    if cancel_token and cancel_token.is_set():
                        logger.info("Generation aborted by user mid-stream.")
                        break

                    if ai_message_chunk is None:
                        ai_message_chunk = chunk
                    else:
                        ai_message_chunk += chunk

                    if chunk.content:
                        yield {
                            "type": "token",
                            "content": chunk.content,
                            "correlation_id": get_correlation_id(),
                        }

                if ai_message_chunk is not None:
                    self._log_ai_message_chunk(ai_message_chunk)

                if not ai_message_chunk or not getattr(ai_message_chunk, "tool_calls", []):
                    if ai_message_chunk is not None:
                        working_messages.append(self._to_ai_message(ai_message_chunk))
                    yield {
                        "type": "done",
                        "correlation_id": get_correlation_id(),
                    }
                    break

                tool_results = []
                pending_pause = None

                for tool_call in ai_message_chunk.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call["id"]

                    yield {
                        "type": "tool_start",
                        "name": tool_name,
                        "args": tool_args,
                        "correlation_id": get_correlation_id(),
                    }

                    try:
                        act = next((a for a in self.engine.actions if a.name == tool_name), None)

                        if act and act.type == "internal" and self.internal_handler:
                            if act.requires_confirmation:
                                pending_pause = {
                                    "type": "pause",
                                    "reason": "confirmation_required",
                                    "action_name": tool_name,
                                    "params": tool_args,
                                    "tool_call_id": tool_id,
                                }
                                break

                            if inspect.iscoroutinefunction(self.internal_handler):
                                result = await self.internal_handler(tool_name, tool_args)
                            else:
                                result = self.internal_handler(tool_name, tool_args)

                            result_str = str(result)
                            yield {
                                "type": "tool_end",
                                "name": tool_name,
                                "result": result_str,
                                "correlation_id": get_correlation_id(),
                            }
                            tool_results.append((tool_id, result_str))

                        else:
                            tool = next((t for t in self.tools if t.name == tool_name), None)
                            if not tool:
                                raise ExecutionException(f"Tool '{tool_name}' is not recognized.")

                            result = await tool.ainvoke(tool_args)
                            result_str = str(result)

                            yield {
                                "type": "tool_end",
                                "name": tool_name,
                                "result": result_str,
                                "correlation_id": get_correlation_id(),
                            }
                            tool_results.append((tool_id, result_str))

                    except ActionRequiresConfirmationError as e:
                        logger.info(f"Execution PAUSED: Tool {tool_name} requires user confirmation.")
                        pending_pause = {
                            "type": "pause",
                            "reason": "confirmation_required",
                            "action_name": e.action_name,
                            "params": e.params,
                            "tool_call_id": tool_id,
                        }
                        break

                    except (OllamaConnectionError, OllamaModelError, ProviderAuthenticationError, ProviderTimeoutError, EmbeddingProviderError, EmbeddingGenerationError) as e:
                        # Infrastructure errors - use simplified machine-readable markers
                        error_type = type(e).__name__
                        
                        if isinstance(e, OllamaConnectionError):
                            error_msg = "INFRASTRUCTURE_ERROR: Ollama server unavailable"
                        elif isinstance(e, OllamaModelError):
                            error_msg = "INFRASTRUCTURE_ERROR: Embedding model not available"
                        elif isinstance(e, ProviderAuthenticationError):
                            error_msg = "INFRASTRUCTURE_ERROR: Provider authentication failed"
                        elif isinstance(e, ProviderTimeoutError):
                            error_msg = "INFRASTRUCTURE_ERROR: Provider request timeout"
                        else:
                            error_msg = "INFRASTRUCTURE_ERROR: Embedding service failed"
                        
                        # Log detailed error for debugging
                        logger.error(f"{error_type}: {str(e)}")
                        
                        yield {
                            "type": "tool_error",
                            "name": tool_name,
                            "error": error_msg,
                            "correlation_id": get_correlation_id(),
                        }
                        tool_results.append((tool_id, error_msg))
                    
                    except Exception as e:
                        # Other errors - classify based on exception type
                        error_type = type(e).__name__
                        error_str = str(e)
                        
                        if isinstance(e, (ConnectionError, TimeoutError)):
                            error_msg = f"INFRASTRUCTURE_ERROR: Network connectivity issue"
                            logger.error(f"{error_type}: {error_str}")
                        elif "validation" in error_type.lower() or "invalid" in error_str.lower():
                            error_msg = f"VALIDATION_ERROR: Invalid input parameters"
                            logger.error(f"{error_type}: {error_str}")
                        else:
                            error_msg = f"TOOL_EXECUTION_ERROR: {error_str}"
                            logger.error(f"{error_type}: {error_str}")
                        
                        yield {
                            "type": "tool_error",
                            "name": tool_name,
                            "error": error_msg,
                            "correlation_id": get_correlation_id(),
                        }
                        tool_results.append((tool_id, error_msg))

                if pending_pause:
                    yield {
                        **pending_pause,
                        "correlation_id": get_correlation_id(),
                        "_resume_state": {
                            "assistant_message": ai_message_chunk.model_dump(mode="json") if hasattr(ai_message_chunk, "model_dump") else str(ai_message_chunk),
                            "completed_tool_results": [
                                {"tool_call_id": tid, "content": content}
                                for tid, content in tool_results
                            ],
                        }
                    }
                    return

                working_messages.append(self._to_ai_message(ai_message_chunk))
                for tool_id, result_str in tool_results:
                    working_messages.append(self._make_tool_message(tool_id, result_str))
        finally:
            if token is not None:
                set_correlation_id(None)