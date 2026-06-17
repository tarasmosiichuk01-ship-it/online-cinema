from unittest.mock import patch, MagicMock

import pytest
import stripe
from sqlalchemy.exc import IntegrityError

from models.orders import Order, OrderStatusEnum, OrderItem
from models.payments import Payment, PaymentStatusEnum


@pytest.mark.asyncio
async def test_create_checkout_session_stripe_error(authorized_client, test_movie, db_session_commit):
    """
    Test creating a checkout session when Stripe returns an error.

    Ensures that the endpoint returns a 503 status code and an appropriate
    error message when a StripeError occurs during checkout session creation.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
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

    with patch(
        "stripe.checkout.Session.create_async",
        side_effect=stripe.error.StripeError("Stripe error")
    ):
        response = await client.post(
            "/api/v1/payments/payments/create-checkout-session",
            json={"order_id": order.id}
        )

    assert response.status_code == 503

    await db_session_commit.delete(order_item)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_checkout_session_integrity_error(authorized_client, test_movie, db_session_commit):
    """
    Test creating a checkout session when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during payment saving.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
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

    mock_session = MagicMock()
    mock_session.id = "test_session_id"
    mock_session.url = "https://stripe.com/test"

    simulated_error = IntegrityError(statement="INSERT INTO payments ...", params={}, orig=Exception())

    with patch("stripe.checkout.Session.create_async", return_value=mock_session):
        with patch("routes.payments.AsyncSession.commit", side_effect=simulated_error):
            response = await client.post(
                "/api/v1/payments/payments/create-checkout-session",
                json={"order_id": order.id}
            )

    assert response.status_code == 400
    assert response.json()["detail"] == "Database error: Could not save payment transaction."

    await db_session_commit.rollback()
    await db_session_commit.delete(order_item)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_refund_order_stripe_error(authorized_client, test_movie, db_session_commit):
    """
    Test refunding an order when Stripe returns an error.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when a StripeError occurs during refund processing.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PAID,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status=PaymentStatusEnum.SUCCESSFUL,
        amount=test_movie.price,
        external_payment_id="test_session_id",
        payment_intent_id="test_intent_id",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    with patch(
        "stripe.Refund.create",
        side_effect=stripe.error.StripeError("Stripe error")
    ):

        response = await client.post(f"/api/v1/payments/orders/{order.id}/refund")

    assert response.status_code == 400
    assert "Stripe error" in response.json()["detail"]

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()
