from datetime import datetime

from pydantic import BaseModel, Field


class TransactionOut(BaseModel):
    id: int
    user_id: str
    merchant: str
    amount: float
    category: str
    timestamp: datetime
    description: str | None = None

    class Config:
        from_attributes = True


class QueryRequest(BaseModel):
    """Payload sent from the frontend chat to the agent."""
    query: str = Field(..., min_length=1, max_length=2000, description="User query (max 2000 chars)")
    user_id: str = Field("user_1", max_length=50)
    session_id: str | None = Field(None, max_length=100)


class QueryResponse(BaseModel):
    """Final response returned after streaming completes."""
    answer: str
    tools_used: list[str] = []


class AnalyticsResponse(BaseModel):
    """Generic wrapper for analytics endpoints."""
    data: dict | list
