# ai_engine/agent_runner.py

import logging
from typing import AsyncGenerator, List, Dict, Any

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage

from .action_engine import ActionEngine
from .providers import ModelFactory
from .exceptions import ActionRequiresConfirmationError

logger = logging.getLogger("AgentRunner")

class AgentRunner:
    def __init__(self, action_engine: ActionEngine, internal_handler=None):
        self.engine = action_engine
        self.internal_handler = internal_handler
        
        # Build tools for all active actions (internal included, for LLM schema visibility)
        self.tools = self.engine.build_tools()
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
        """
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=self.system_prompt))
            
        while True:
            ai_message_chunk = None
            
            async for chunk in self.llm_with_tools.astream(messages):
                if ai_message_chunk is None:
                    ai_message_chunk = chunk
                else:
                    ai_message_chunk += chunk
                    
                if chunk.content:
                    yield {"type": "token", "content": chunk.content}
            
            messages.append(ai_message_chunk)
            
            if not ai_message_chunk.tool_calls:
                yield {"type": "done"}
                break
                
            for tool_call in ai_message_chunk.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                yield {"type": "tool_start", "name": tool_name, "args": tool_args}
                
                try:
                    act = next((a for a in self.engine.actions if a.name == tool_name), None)
                    
                    if act and act.type == "internal" and self.internal_handler:
                        if act.requires_confirmation:
                            yield {
                                "type": "pause",
                                "reason": "confirmation_required",
                                "action_name": tool_name,
                                "params": tool_args,
                                "tool_call_id": tool_id
                            }
                            return
                        
                        result = await self.internal_handler(tool_name, tool_args)
                        result_str = str(result)
                        yield {"type": "tool_end", "name": tool_name, "result": result_str}
                        messages.append(ToolMessage(content=result_str, tool_call_id=tool_id))
                    else:
                        tool = next((t for t in self.tools if t.name == tool_name), None)
                        if not tool:
                            raise ValueError(f"Tool '{tool_name}' is not recognized.")
                            
                        result = await tool.ainvoke(tool_args)
                        result_str = str(result)
                        
                        yield {"type": "tool_end", "name": tool_name, "result": result_str}
                        messages.append(ToolMessage(content=result_str, tool_call_id=tool_id))
                        
                except ActionRequiresConfirmationError as e:
                    logger.info(f"Execution PAUSED: Tool {tool_name} requires user confirmation.")
                    yield {
                        "type": "pause",
                        "reason": "confirmation_required",
                        "action_name": e.action_name,
                        "params": e.params,
                        "tool_call_id": tool_id
                    }
                    return 
                    
                except Exception as e:
                    error_msg = f"Error executing tool: {str(e)}"
                    logger.error(error_msg)
                    yield {"type": "tool_error", "name": tool_name, "error": error_msg}
                    messages.append(ToolMessage(content=error_msg, tool_call_id=tool_id))