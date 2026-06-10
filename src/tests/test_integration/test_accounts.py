import pytest


@pytest.mark.asyncio
async def test_register_user(client):
    payload = {
        "email": "testuser@example.com",
        "password": "Test1234!",
    }

    response = await client.post("/api/v1/accounts/register/", json=payload)
    assert response.status_code == 201