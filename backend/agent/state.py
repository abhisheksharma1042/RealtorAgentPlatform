"""Agent state management for LangGraph"""

from typing import TypedDict, List, Dict, Any
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the DFW Realtor Agent"""
    messages: List[BaseMessage]
    user_query: str
    context: Dict[str, Any]
    tools_used: List[str]
