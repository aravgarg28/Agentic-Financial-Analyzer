"""
Redis-backed conversational memory for the ReAct agent.
Each session is keyed by user_id:session_id with a 24-hour TTL.
"""
from __future__ import annotations

import json
from typing import Optional

import redis.asyncio as aioredis
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

from app.config import settings

_redis: Optional[aioredis.Redis] = None
TTL_SECONDS = 86400  # 24 hours
MAX_HISTORY = 20     # keep last 20 messages per session


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _key(user_id: str, session_id: str) -> str:
    return f"chat:{user_id}:{session_id}"


def _serialize_message(msg: BaseMessage) -> str:
    return json.dumps({"type": msg.type, "content": msg.content})


def _deserialize_message(raw: str) -> BaseMessage:
    data = json.loads(raw)
    if data["type"] == "human":
        return HumanMessage(content=data["content"])
    return AIMessage(content=data["content"])


async def load_memory(user_id: str, session_id: str) -> list[BaseMessage]:
    """Load chat history for a session from Redis."""
    r = await get_redis()
    key = _key(user_id, session_id)
    raw_list = await r.lrange(key, 0, -1)
    return [_deserialize_message(raw) for raw in raw_list]


async def save_messages(
    user_id: str, session_id: str, messages: list[BaseMessage]
) -> None:
    """Append new messages to session history and refresh TTL."""
    r = await get_redis()
    key = _key(user_id, session_id)
    pipe = r.pipeline()
    for msg in messages:
        pipe.rpush(key, _serialize_message(msg))
    # Trim to MAX_HISTORY
    pipe.ltrim(key, -MAX_HISTORY, -1)
    pipe.expire(key, TTL_SECONDS)
    await pipe.execute()


async def clear_memory(user_id: str, session_id: str) -> None:
    """Clear a session's history."""
    r = await get_redis()
    await r.delete(_key(user_id, session_id))
