"""
LangChain ReAct agent wired to Groq LLM with 8 financial tools.
Supports streaming via SSE.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.agent.memory import load_memory, save_messages
from app.agent.tools import ALL_TOOLS
from app.config import settings

# System prompt for the financial analyst persona
SYSTEM_PROMPT = """You are an expert AI financial analyst assistant. You have access to a user's
transaction database and powerful analytical tools. Your job is to help users understand their
spending habits, detect anomalies, track budgets, and provide actionable financial insights.

Guidelines:
- Always use the appropriate tools to fetch real data before answering.
- Present numbers clearly with currency formatting ($X,XXX.XX).
- When comparing periods, show percentage changes.
- Flag any concerning spending patterns proactively.
- Be concise but thorough. Use bullet points for readability.
- If the user asks something you cannot answer with the available tools, say so honestly.
- When multiple tools could help, use them in combination for richer answers.
- Always specify the user_id parameter when calling tools.
"""


def _build_llm():
    """Construct a Groq-backed LLM."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=settings.groq_api_key,
        temperature=0.1,
        max_tokens=4096,
        streaming=True,
    )


async def run_agent_stream(
    query: str,
    user_id: str = "user_1",
    session_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Run the ReAct agent and yield SSE-style events:
      {"event": "thought",   "data": "..."}
      {"event": "tool_call", "data": {"tool": "...", "input": ...}}
      {"event": "tool_result", "data": "..."}
      {"event": "answer",    "data": "..."}
      {"event": "error",     "data": "..."}
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    llm = _build_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    tools_map = {t.name: t for t in ALL_TOOLS}
    tools_used: list[str] = []

    # Load conversation history from Redis
    history = await load_memory(user_id, session_id)

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + history + [HumanMessage(content=query)]

    max_iterations = 10
    iteration = 0

    try:
        while iteration < max_iterations:
            iteration += 1

            # Call LLM
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            # Check for tool calls
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    # Ensure user_id is passed
                    if "user_id" not in tool_args:
                        tool_args["user_id"] = user_id

                    yield {"event": "tool_call", "data": {"tool": tool_name, "input": tool_args}}

                    # Execute the tool
                    tool_fn = tools_map.get(tool_name)
                    if tool_fn:
                        try:
                            result = await tool_fn.ainvoke(tool_args)
                            tools_used.append(tool_name)
                        except Exception as e:
                            result = f"Error executing {tool_name}: {str(e)}"

                        yield {"event": "tool_result", "data": result[:500] if len(str(result)) > 500 else result}

                        # Add tool result as message
                        from langchain_core.messages import ToolMessage
                        messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
                    else:
                        from langchain_core.messages import ToolMessage
                        messages.append(ToolMessage(content=f"Unknown tool: {tool_name}", tool_call_id=tool_call["id"]))
            else:
                # No tool calls — this is the final answer
                answer = response.content
                yield {"event": "answer", "data": answer}

                # Save conversation to Redis
                await save_messages(user_id, session_id, [
                    HumanMessage(content=query),
                    AIMessage(content=answer),
                ])
                return

        # Hit max iterations
        yield {"event": "answer", "data": "I've reached my reasoning limit. Here's what I found so far based on the tools I used."}

    except Exception as e:
        yield {"event": "error", "data": str(e)}
