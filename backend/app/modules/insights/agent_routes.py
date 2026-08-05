"""Agent query endpoint (T-021/T-030): SSE stream bound to the session Principal.

The household comes from the cookie session; the client may supply only a
free-form ``conversation_id`` for grouping turns — the Redis key is built
server-side as ``chat:{household_id}:{conversation_id}`` so it can never address
another tenant's memory (AGT-05). Rate limited per user (AGT-06 / SEC-04).
"""
from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.memory import conversation_key
from app.agent.react_agent import run_agent_stream
from app.modules.common import ratelimit
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.service import Principal

router = APIRouter(prefix="/agent", tags=["Agent"])

# Conversation ids are client-chosen but constrained to a safe charset so they
# cannot inject separators into the Redis key.
_CONV_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AgentQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = Field(None, max_length=64)


def _agent_rate_limit(principal: Principal) -> None:
    ratelimit._enforce(
        f"agent:user:{principal.user_id}", ratelimit.AGENT_PER_USER
    )


@router.post("/query")
async def agent_query(
    req: AgentQuery,
    request: Request,
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> StreamingResponse:
    _agent_rate_limit(principal)

    conversation_id = req.conversation_id or uuid.uuid4().hex
    if not _CONV_RE.match(conversation_id):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation_id",
        )
    memory_key = conversation_key(principal.household_id, conversation_id)

    async def event_generator():
        yield f"data: {json.dumps({'event': 'conversation', 'data': conversation_id})}\n\n"
        async for event in run_agent_stream(
            query=req.query,
            household_id=principal.household_id,
            memory_key=memory_key,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
