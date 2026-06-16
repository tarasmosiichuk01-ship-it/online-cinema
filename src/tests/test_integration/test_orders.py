import pytest


@pytest.mark.asyncio
async def test_create_order_unauthorized_user(client):
    """
    Test creating an order by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to create an order.
    """
    response = await client.post("/api/v1/orders/orders")

    assert response.status_code == 401

    assert response.json()["detail"] == "Not authenticated"

