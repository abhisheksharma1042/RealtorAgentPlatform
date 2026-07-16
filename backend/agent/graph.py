"""LangGraph agent orchestration for DFW Realtor Assistant"""

import os
import json
from typing import AsyncIterator, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.state import AgentState
from agent.prompts import get_system_prompt
from agent.tools import TOOLS, TOOL_FUNCTIONS
from backend.hermes.memory import build_memory_block


# Initialize Claude model
def get_model():
    """Initialize the Claude model with tools"""
    model = ChatAnthropic(
        model="claude-sonnet-4-5",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.7,
    )
    return model.bind_tools(TOOLS)


async def call_agent(state: AgentState) -> AgentState:
    """Agent node - calls Claude to decide next action"""
    model = get_model()

    # Build messages with system prompt
    memory_block = state.get("context", {}).get("memory_block", "")
    system_message = {"role": "system", "content": get_system_prompt() + memory_block}
    messages = [system_message] + state["messages"]

    response = await model.ainvoke(messages)

    # Update state
    state["messages"].append(response)

    return state


async def call_tools(state: AgentState) -> AgentState:
    """Tool node - executes requested tools"""
    last_message = state["messages"][-1]

    # Extract tool calls from the message
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_results = []

        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            # Execute tool
            if tool_name in TOOL_FUNCTIONS:
                result = await TOOL_FUNCTIONS[tool_name](**tool_args)
                tool_results.append(
                    ToolMessage(
                        content=json.dumps(result),
                        tool_call_id=tool_id,
                        name=tool_name
                    )
                )
                state["tools_used"].append(tool_name)

        # Add tool results to messages
        state["messages"].extend(tool_results)

    return state


def should_continue(state: AgentState) -> str:
    """Determine if we should continue or end"""
    last_message = state["messages"][-1]

    # If the last message has tool calls, execute them
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # Otherwise, we're done
    return "end"


# Build the graph
def create_agent_graph():
    """Create the LangGraph workflow"""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", call_agent)
    workflow.add_node("tools", call_tools)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )

    # After tools, go back to agent
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# Create the compiled graph
agent_graph = create_agent_graph()


async def stream_agent_response(user_message: str) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream agent responses using Server-Sent Events format

    Yields:
        Dict with event type and data
    """
    # Load memory once per request (not per agent-node hop) - it is small
    # and deterministic; failure degrades to a no-memory turn.
    memory_block = await build_memory_block()

    # Initialize state
    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_message)],
        "user_query": user_message,
        "context": {"memory_block": memory_block},
        "tools_used": []
    }

    # Stream through the graph
    async for event in agent_graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_output in event.items():
            # Get the last message
            if "messages" in node_output and node_output["messages"]:
                last_message = node_output["messages"][-1]

                # Handle AI messages
                if isinstance(last_message, AIMessage):
                    content_str = last_message.content
                    if isinstance(content_str, list):
                        # Extract text from content blocks
                        text_blocks = [
                            blk["text"] 
                            for blk in content_str 
                            if isinstance(blk, dict) and blk.get("type") == "text" and "text" in blk
                        ]
                        content_str = "".join(text_blocks)
                        
                    if content_str:
                        yield {
                            "type": "agent_message",
                            "content": content_str,
                            "node": node_name
                        }

                    # Handle tool calls
                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        for tool_call in last_message.tool_calls:
                            yield {
                                "type": "tool_call",
                                "tool": tool_call["name"],
                                "args": tool_call["args"]
                            }

                # Handle tool results
                elif isinstance(last_message, ToolMessage):
                    result = json.loads(last_message.content)
                    yield {
                        "type": "tool_result",
                        "tool": last_message.name,
                        "result": result
                    }

    # Final event
    yield {"type": "complete"}
