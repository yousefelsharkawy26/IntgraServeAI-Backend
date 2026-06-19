# ai_engine/agent_runner.py

import asyncio
import inspect
import logging
from typing import AsyncGenerator, List, Dict, Any

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage

from .action_engine import ActionEngine
from .providers import ModelFactory
from .exceptions import ActionRequiresConfirmationError, ParsingException

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, action_engine: ActionEngine, internal_handler=None):
        self.engine = action_engine
        self.internal_handler = internal_handler

        # Build tools for all active actions (internal included, for LLM schema visibility)
        self.tools = self.engine.build_tools()

        # P0.4: Explicit null-guard for llm_config with a clear, actionable error
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

    async def stream_chat(self, messages: List[BaseMessage]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams the AI's response token-by-token.
        Automatically handles tool execution and pauses for user confirmation.

        Yields:
            Dict with keys:
                - "type": "token" | "done" | "tool_start" | "tool_end" | "tool_error" | "pause"
                - Additional keys depending on type

        Resume state (for "pause" events):
            The pause event includes a "_resume_state" key containing the assistant
            message and completed tool results. The caller must reconstruct the
            conversation history and call stream_chat again.
        """
        # P2.2: Defensive copy to avoid mutating the caller's list in-place
        working_messages = list(messages)

        if not working_messages or not isinstance(working_messages[0], SystemMessage):
            working_messages.insert(0, SystemMessage(content=self.system_prompt))

        # P2.4: Extract rate-limit delay from config for async sleep between LLM calls
        rate_limit_delay = 0
        if self.engine.agent_config.llm_config:
            rate_limit_delay = self.engine.agent_config.llm_config.rate_limit_delay_seconds or 0

        first_iteration = True

        while True:
            # P2.4: Async rate limiting between LLM calls (never blocks the event loop)
            if not first_iteration and rate_limit_delay > 0:
                logger.info(
                    f"Rate Limiter: Sleeping for {rate_limit_delay}s to respect API quotas..."
                )
                await asyncio.sleep(rate_limit_delay)
            first_iteration = False

            ai_message_chunk = None

            async for chunk in self.llm_with_tools.astream(working_messages):
                if ai_message_chunk is None:
                    ai_message_chunk = chunk
                else:
                    ai_message_chunk += chunk

                if chunk.content:
                    yield {"type": "token", "content": chunk.content}

            if not ai_message_chunk or not getattr(ai_message_chunk, "tool_calls", []):
                # No tool calls — safe to append and finish
                if ai_message_chunk is not None:
                    working_messages.append(ai_message_chunk)
                yield {"type": "done"}
                break

            # P2.1: We have tool calls. Do NOT append the assistant message yet.
            # Collect all tool results atomically before committing to the history.
            tool_results = []
            pending_pause = None

            for tool_call in ai_message_chunk.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                yield {"type": "tool_start", "name": tool_name, "args": tool_args}

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

                        # P2.3: Detect sync vs async internal_handler and adapt invocation
                        if inspect.iscoroutinefunction(self.internal_handler):
                            result = await self.internal_handler(tool_name, tool_args)
                        else:
                            result = self.internal_handler(tool_name, tool_args)

                        result_str = str(result)
                        yield {"type": "tool_end", "name": tool_name, "result": result_str}
                        tool_results.append((tool_id, result_str))

                    else:
                        tool = next((t for t in self.tools if t.name == tool_name), None)
                        if not tool:
                            raise ValueError(f"Tool '{tool_name}' is not recognized.")

                        result = await tool.ainvoke(tool_args)
                        result_str = str(result)

                        yield {"type": "tool_end", "name": tool_name, "result": result_str}
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

                except Exception as e:
                    error_msg = f"Error executing tool: {str(e)}"
                    logger.error(error_msg)
                    yield {"type": "tool_error", "name": tool_name, "error": error_msg}
                    tool_results.append((tool_id, error_msg))

            if pending_pause:
                # P2.1: Yield pause with resume state so the caller can reconstruct
                # the conversation history. Do NOT append the assistant message or
                # any ToolMessages to working_messages.
                yield {
                    **pending_pause,
                    "_resume_state": {
                        "assistant_message": ai_message_chunk,
                        "completed_tool_results": [
                            {"tool_call_id": tid, "content": content}
                            for tid, content in tool_results
                        ],
                    }
                }
                return

            # P2.1: All tool calls completed successfully. Commit atomically.
            working_messages.append(ai_message_chunk)
            for tool_id, result_str in tool_results:
                working_messages.append(ToolMessage(content=result_str, tool_call_id=tool_id))