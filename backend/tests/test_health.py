import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


@pytest.mark.asyncio
async def test_liveness():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
