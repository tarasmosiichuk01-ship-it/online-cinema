import pytest
from sqlalchemy.sql.functions import current_user

from models.orders import Order, OrderStatusEnum, OrderItem


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


@pytest.mark.asyncio
async def test_create_checkout_session_total_amount_mismatch(authorized_client, test_movie, db_session_commit):
    """
    Test creating a checkout session when total amount does not match order items.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the order total amount does not match the sum
    of order items prices.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=99999.99,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    order_item = OrderItem(
        order_id=order.id,
        movie_id=test_movie.id,
        price_at_order=test_movie.price,
    )
    db_session_commit.add(order_item)
    await db_session_commit.commit()

    payload = {
        "order_id": order.id
    }

    response = await client.post("/api/v1/payments/payments/create-checkout-session", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Order total amount mismatch with items configuration."

    await db_session_commit.delete(order_item)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_refund_order_unauthorized_user(client):
    """
    Test refunding an order by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to refund an order.
    """
    response = await client.post("/api/v1/payments/orders/1/refund")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_refund_order_if_order_not_found(authorized_client):
    """
    Test refunding an order that does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no order with the given ID exists for the current user.
    """
    client, user = authorized_client

    response = await client.post("/api/v1/payments/orders/99999999/refund")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.asyncio
async def test_get_payments_success_unauthorized_user(client):
    """
    Test getting payment success page by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to access
    the payment success page.
    """
    response = await client.get(
        "/api/v1/payments/payments/success?session_id=test_session_id"
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


