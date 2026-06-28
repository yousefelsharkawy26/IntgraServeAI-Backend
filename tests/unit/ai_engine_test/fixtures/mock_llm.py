"""
Mock LLM Fixtures — Phase 3 Async & Runner Infrastructure

Provides configurable mock implementations of LangChain's BaseChatModel
that yield AIMessageChunk sequences for testing AgentRunner.stream_chat().

The core challenge in testing AgentRunner is that it depends on:
  1. llm_with_tools.astream(messages) → yields AIMessageChunk
  2. ai_message_chunk.tool_calls → list of dicts with name/args/id
  3. tool.ainvoke(tool_args) → returns result string

We mock layer (1) and (3), letting the runner exercise layer (2) and its
state machine logic.

Implementation approach:
  - Create a FakeLLM class that implements astream() as an async generator.
  - Pre-configure it with a sequence of "turns" (each turn = list of chunks).
  - Each chunk is an AIMessageChunk with optional tool_calls.
  - Support additive chunking (chunk + chunk = full message) exactly like
    the real LangChain behavior.
  - Provide a tool-invoke mock that returns deterministic strings.
"""

import json
from typing import List, Dict, AsyncGenerator

import pytest
from langchain_core.messages import AIMessageChunk


class FakeLLM:
    """
    A deterministic mock LLM for testing AgentRunner.

    Configure with a list of 'turns'. Each turn is a list of AIMessageChunk
    objects that will be yielded when astream() is called. After all turns
    are consumed, subsequent calls yield an empty done message.
    """

    def __init__(self, turns: List[List[AIMessageChunk]] = None):
        self.turns = turns or []
        self._turn_index = 0
        self._call_history: List[List[Dict]] = []  # record tool_calls per turn

    def bind_tools(self, tools):
        """Return self so the runner can call astream on the bound object."""
        self._tools = tools
        return self

    async def astream(self, messages) -> AsyncGenerator[AIMessageChunk, None]:
        """
        Yield chunks for the current turn, then advance the turn counter.
        """
        if self._turn_index < len(self.turns):
            turn = self.turns[self._turn_index]
            self._turn_index += 1
            for chunk in turn:
                yield chunk
        else:
            # No more turns: yield empty done message
            yield AIMessageChunk(content="")

    def reset(self):
        self._turn_index = 0

    @property
    def call_history(self) -> List[List[Dict]]:
        return self._call_history


def make_text_chunks(text: str, tool_calls: List[Dict] = None) -> List[AIMessageChunk]:
    """
    Create a single-turn chunk sequence that yields a text-only response.

    Args:
        text: The content string to yield.
        tool_calls: Optional list of tool call dicts. If provided, the
            final chunk will have tool_calls set.
    """
    chunks = []
    # Split text into character chunks to simulate real streaming
    for i, char in enumerate(text):
        kwargs = {"content": char}
        if i == len(text) - 1 and tool_calls:
            kwargs["tool_calls"] = tool_calls
            kwargs["tool_call_chunks"] = [
                {"name": tc["name"], "args": tc["args"], "id": tc["id"], "index": idx}
                for idx, tc in enumerate(tool_calls)
            ]
        chunks.append(AIMessageChunk(**kwargs))
    if not chunks:
        chunks.append(AIMessageChunk(content=""))
    return chunks


def make_tool_call_chunks(tool_calls: List[Dict]) -> List[AIMessageChunk]:
    """
    Create a single-turn chunk sequence that yields ONLY tool calls
    (no text content). This is the common pattern when the LLM decides
    to invoke a tool without preamble text.
    """
    chunks = []
    for idx, tc in enumerate(tool_calls):
        args_data = tc.get("args", {})
        
        args_dict = args_data if isinstance(args_data, dict) else json.loads(args_data)
        args_str = json.dumps(args_data) if isinstance(args_data, dict) else args_data

        kwargs = {
            "content": "",
            "tool_calls": [{
                "name": tc["name"],
                "args": args_dict,
                "id": tc["id"]
            }] if idx == len(tool_calls) - 1 else [],
            "tool_call_chunks": [{
                "name": tc["name"],
                "args": args_str,  # <--- Must be a string here
                "id": tc["id"],
                "index": idx
            }]
        }
        chunks.append(AIMessageChunk(**kwargs))
    return chunks


@pytest.fixture
def mock_llm_factory():
    """Factory fixture that returns a configured FakeLLM."""
    def _make(turns=None):
        return FakeLLM(turns=turns)
    return _make


@pytest.fixture
def text_only_llm(mock_llm_factory):
    """LLM that always responds with plain text, no tool calls."""
    return mock_llm_factory(turns=[
        make_text_chunks("Hello, how can I help you?")
    ])


@pytest.fixture
def single_tool_llm(mock_llm_factory):
    """LLM that invokes one tool then responds with text."""
    return mock_llm_factory(turns=[
        make_tool_call_chunks([
            {"name": "get_order_details", "args": {"order_id": "ORD-123"}, "id": "call_1"}
        ]),
        make_text_chunks("Your order ORD-123 is shipped.")
    ])


@pytest.fixture
def multi_tool_llm(mock_llm_factory):
    """LLM that invokes two tools in one turn, then responds."""
    return mock_llm_factory(turns=[
        make_tool_call_chunks([
            {"name": "get_order_details", "args": {"order_id": "ORD-123"}, "id": "call_1"},
            {"name": "check_store_hours", "args": {"city": "New York"}, "id": "call_2"}
        ]),
        make_text_chunks("Your order is shipped. Stores open 9-5.")
    ])


@pytest.fixture
def confirmation_tool_llm(mock_llm_factory):
    """LLM that invokes a tool requiring confirmation."""
    return mock_llm_factory(turns=[
        make_tool_call_chunks([
            {"name": "update_shipping_address", "args": {
                "order_id": "ORD-999",
                "new_street": "123 Main St",
                "new_zip": "10001"
            }, "id": "call_1"}
        ])
    ])


@pytest.fixture
def error_tool_llm(mock_llm_factory):
    """LLM that invokes a tool that will raise an exception."""
    return mock_llm_factory(turns=[
        make_tool_call_chunks([
            {"name": "get_order_details", "args": {"order_id": "BAD"}, "id": "call_1"}
        ]),
        make_text_chunks("I encountered an error. Please try again.")
    ])


@pytest.fixture
def hallucinated_tool_llm(mock_llm_factory):
    """LLM that invokes a non-existent tool name."""
    return mock_llm_factory(turns=[
        make_tool_call_chunks([
            {"name": "fake_tool", "args": {"x": 1}, "id": "call_1"}
        ])
    ])


@pytest.fixture
def empty_response_llm(mock_llm_factory):
    """LLM that yields zero content chunks."""
    return mock_llm_factory(turns=[
        [AIMessageChunk(content="")]
    ])


@pytest.fixture
def internal_confirmation_llm(mock_llm_factory):
    """LLM that invokes an internal action requiring confirmation."""
    return mock_llm_factory(turns=[
        make_tool_call_chunks([
            {"name": "escalate_to_human", "args": {}, "id": "call_1"}
        ])
    ])
