import pytest


@pytest.mark.asyncio
async def test_create_checkout_session_unauthorized_user(client):
    """
    Test creating a checkout session by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to create
    a checkout session.
    """
    payload = {
        "order_id": 1
    }

    response = await client.post("/api/v1/payments/payments/create-checkout-session", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

