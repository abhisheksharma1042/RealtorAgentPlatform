"""Regression tests for the graph's memory-injection invariants."""
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from backend.agent import graph


class FakeModel:
    """Stand-in for the tool-bound ChatAnthropic model returned by get_model()."""

    def __init__(self, captured):
        self._captured = captured

    async def ainvoke(self, messages):
        self._captured["messages"] = messages
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_call_agent_appends_memory_block_to_system_prompt():
    captured = {}
    state = {
        "messages": [],
        "user_query": "hi",
        "context": {"memory_block": "\n\n# Hermes context\nMEMORY_SENTINEL"},
        "tools_used": [],
    }

    with patch.object(graph, "get_model", return_value=FakeModel(captured)):
        result = await graph.call_agent(state)

    system = captured["messages"][0]
    content = system["content"] if isinstance(system, dict) else system.content
    assert "MEMORY_SENTINEL" in content
    # response gets appended to the same state's messages
    assert result["messages"][-1].content == "ok"


@pytest.mark.asyncio
async def test_call_agent_tolerates_missing_context():
    captured = {}
    state = {
        "messages": [],
        "user_query": "hi",
        "tools_used": [],
        # no "context" key at all
    }

    with patch.object(graph, "get_model", return_value=FakeModel(captured)):
        result = await graph.call_agent(state)

    system = captured["messages"][0]
    content = system["content"] if isinstance(system, dict) else system.content
    # falls back to empty string - system prompt is present, no memory block appended
    assert content == graph.get_system_prompt()
    assert result["messages"][-1].content == "ok"


@pytest.mark.asyncio
async def test_stream_agent_response_loads_memory_once(monkeypatch):
    calls = []

    async def fake_build(*args, **kwargs):
        calls.append(1)
        return "\n\nMEM"

    monkeypatch.setattr(graph, "build_memory_block", fake_build)

    class FakeCompiledGraph:
        async def astream(self, initial_state, stream_mode="updates"):
            # Async generator that yields nothing - just exercises the
            # streaming loop without invoking the real LangGraph/LLM.
            return
            yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(graph, "agent_graph", FakeCompiledGraph())

    events = [event async for event in graph.stream_agent_response("hello")]

    assert calls == [1]
    assert events == [{"type": "complete"}]
