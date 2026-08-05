"""Agent stopgap hardening (T-030, AGT-01/02).

Drives ``run_agent_stream`` with a stub LLM that emits hostile tool calls
(attempting to pass a foreign user_id/household_id and to mutate a budget) and
asserts the agent cannot read another tenant's rows nor mutate anything. Uses
the model layer for arranging data; Redis memory is stubbed out.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.agent import react_agent
from tests.helpers import add_account, add_category, add_transaction, make_household


class _FakeToolCallMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _FakeFinalMessage:
    def __init__(self, content):
        self.tool_calls = []
        self.content = content


class _FakeLLM:
    """Emits one round of tool calls, then a final answer echoing tool output."""

    def __init__(self, tool_calls):
        self._tool_calls = tool_calls
        self._turn = 0
        self.seen_results: list[str] = []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        # Capture any ToolMessage contents to inspect what the tool returned.
        for m in messages:
            if getattr(m, "type", None) == "tool" or m.__class__.__name__ == "ToolMessage":
                self.seen_results.append(str(m.content))
        self._turn += 1
        if self._turn == 1:
            return _FakeToolCallMessage(self._tool_calls)
        return _FakeFinalMessage("done")


@pytest.fixture
def _stub_memory(monkeypatch):
    async def _load(_key):
        return []

    async def _save(_key, _messages):
        return None

    monkeypatch.setattr(react_agent, "load_memory", _load)
    monkeypatch.setattr(react_agent, "save_messages", _save)


async def _drain(gen):
    events = []
    async for e in gen:
        events.append(e)
    return events


async def test_agent_ignores_model_supplied_identity(seed_session, monkeypatch, _stub_memory):
    """AGT-01: a model-injected household_id/user_id is stripped; the tool reads
    only the executor-bound household's data."""
    _, mem_a = await make_household(seed_session, "aa@example.com")
    _, mem_b = await make_household(seed_session, "bb@example.com")
    acct_a = await add_account(seed_session, mem_a.household_id)
    acct_b = await add_account(seed_session, mem_b.household_id)
    cat = await add_category(seed_session, None, "Food")
    await add_transaction(
        seed_session, household_id=mem_a.household_id, account_id=acct_a.id,
        amount_minor=-111, booked_date=date.today(), description="A coffee", category_id=cat.id,
    )
    await add_transaction(
        seed_session, household_id=mem_b.household_id, account_id=acct_b.id,
        amount_minor=-222, booked_date=date.today(), description="B yacht", category_id=cat.id,
    )
    await seed_session.commit()

    # Hostile tool call: try to read household B by passing its id explicitly.
    hostile = [
        {
            "name": "get_spending_by_category",
            "args": {"days": 30, "household_id": mem_b.household_id, "user_id": 999},
            "id": "call_1",
        }
    ]
    fake = _FakeLLM(hostile)
    monkeypatch.setattr(react_agent, "_build_llm", lambda: fake)

    events = await _drain(
        react_agent.run_agent_stream(
            query="show my spending",
            household_id=mem_a.household_id,  # executor-bound tenant = A
            memory_key="chat:test",
        )
    )
    assert any(e["event"] == "answer" for e in events)
    # The tool result must reflect A's data (111), never B's (222).
    all_results = " ".join(fake.seen_results)
    assert "111" in all_results
    assert "222" not in all_results
    # The tool_call event shows identity args were stripped before execution.
    tool_calls = [e for e in events if e["event"] == "tool_call"]
    assert tool_calls
    assert "household_id" not in tool_calls[0]["data"]["input"]
    assert "user_id" not in tool_calls[0]["data"]["input"]


async def test_agent_cannot_mutate(seed_session, monkeypatch, _stub_memory):
    """AGT-02: a model call to a write tool finds no such tool (unknown tool),
    and nothing is mutated."""
    _, mem = await make_household(seed_session, "mut@example.com")
    await seed_session.commit()

    hostile = [
        {"name": "update_budget", "args": {"category": "food", "amount": 0}, "id": "c1"}
    ]
    fake = _FakeLLM(hostile)
    monkeypatch.setattr(react_agent, "_build_llm", lambda: fake)

    events = await _drain(
        react_agent.run_agent_stream(
            query="set my food budget to 0",
            household_id=mem.household_id,
            memory_key="chat:test2",
        )
    )
    # The write tool is not registered, so the executor reports it unknown.
    assert any(e["event"] == "answer" for e in events)
    assert any("Unknown tool" in r for r in fake.seen_results)
