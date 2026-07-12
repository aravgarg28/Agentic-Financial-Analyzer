"""Smoke tests — verify the app boots and serves basic health endpoints."""
from __future__ import annotations

from httpx import AsyncClient


async def test_root_ok(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
