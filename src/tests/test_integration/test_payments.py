import pytest

from models.orders import Order, OrderStatusEnum


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


@pytest.mark.asyncio
async def test_create_checkout_session_if_order_not_found(authorized_client):
    """
    Test creating a checkout session when the order does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no order with the given ID exists for the current user.
    """
    client, user = authorized_client

    payload = {
        "order_id": 9999999
    }

    response = await client.post("/api/v1/payments/payments/create-checkout-session", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"
