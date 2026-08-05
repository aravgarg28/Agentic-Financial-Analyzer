"""
Redis-backed conversational memory for the ReAct agent.
Each session is keyed by user_id:session_id with a 24-hour TTL.
"""
from __future__ import annotations

import json

import redis.asyncio as aioredis
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config import settings

_redis: aioredis.Redis | None = None
TTL_SECONDS = 86400  # 24 hours
MAX_HISTORY = 20     # keep last 20 messages per session


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def conversation_key(household_id: int, conversation_id: str) -> str:
    """Build the Redis memory key from SERVER-derived values only (AGT-05).

    The household id comes from the session, not the client, so one household
    can never read or poison another's conversation memory."""
    return f"chat:{household_id}:{conversation_id}"


def _serialize_message(msg: BaseMessage) -> str:
    return json.dumps({"type": msg.type, "content": msg.content})


def _deserialize_message(raw: str) -> BaseMessage:
    data = json.loads(raw)
    if data["type"] == "human":
        return HumanMessage(content=data["content"])
    return AIMessage(content=data["content"])


async def load_memory(key: str) -> list[BaseMessage]:
    """Load chat history for a conversation key from Redis."""
    r = await get_redis()
    raw_list = await r.lrange(key, 0, -1)
    return [_deserialize_message(raw) for raw in raw_list]


async def save_messages(key: str, messages: list[BaseMessage]) -> None:
    """Append new messages to conversation history and refresh TTL."""
    r = await get_redis()
    pipe = r.pipeline()
    for msg in messages:
        pipe.rpush(key, _serialize_message(msg))
    # Trim to MAX_HISTORY
    pipe.ltrim(key, -MAX_HISTORY, -1)
    pipe.expire(key, TTL_SECONDS)
    await pipe.execute()


async def clear_memory(key: str) -> None:
    """Clear a conversation's history."""
    r = await get_redis()
    await r.delete(key)
