from unittest.mock import patch

import pytest
import stripe

from models.orders import Order, OrderStatusEnum, OrderItem


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