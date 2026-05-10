"""
/agent/query — SSE streaming endpoint for the ReAct agent.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas import QueryRequest
from app.agent.react_agent import run_agent_stream

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/query")
async def agent_query(req: QueryRequest):
    """Stream agent reasoning steps and final answer via SSE."""
    session_id = req.session_id or str(uuid.uuid4())

    async def event_generator():
        # Send session_id first so the frontend can persist it
        yield f"data: {json.dumps({'event': 'session', 'data': session_id})}\n\n"

        async for event in run_agent_stream(
            query=req.query,
            user_id=req.user_id,
            session_id=session_id,
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
