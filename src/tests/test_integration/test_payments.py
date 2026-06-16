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


@pytest.mark.asyncio
async def test_create_checkout_session_if_order_status_not_pending(authorized_client, test_movie, db_session_commit):
    """
    Test creating a checkout session when the order is not in PENDING status.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the user attempts to pay for an order that is
    not in PENDING status.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PAID,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.commit()

    payload = {
        "order_id": order.id
    }

    response = await client.post("/api/v1/payments/payments/create-checkout-session", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "You can only pay for pending orders"

    await db_session_commit.delete(order)
    await db_session_commit.commit()
