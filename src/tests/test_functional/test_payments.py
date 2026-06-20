import pytest

from models.orders import Order, OrderStatusEnum
from models.payments import Payment, PaymentStatusEnum


@pytest.mark.asyncio
async def test_get_payments_canceled_returns_correct_message(client):
    """
    Test that get_payments_canceled returns the correct cancellation message.

    Ensures that the endpoint returns a 200 status code and the appropriate
    cancellation message when a user cancels the payment process.
    """
    response = await client.get("/api/v1/payments/payments/canceled")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert (
        response.json()["message"]
        == "You have canceled the payment. Your order remains pending."
    )


@pytest.mark.asyncio
async def test_get_payments_success_with_all_statuses(
    authorized_client, test_movie, db_session_commit
):
    """
    Test get_payments_success endpoint with different payment statuses.

    Ensures that the endpoint returns correct status and message
    for SUCCESSFUL, PENDING and REFUNDED payment statuses.
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
        external_payment_id="session_successful",
        payment_intent_id="intent_successful",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    response = await client.get(
        f"/api/v1/payments/payments/success?session_id={payment.external_payment_id}"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "Thank you for your purchase!"

    payment.status = PaymentStatusEnum.PENDING
    payment.external_payment_id = "session_pending"
    await db_session_commit.commit()

    response = await client.get(
        f"/api/v1/payments/payments/success?session_id={payment.external_payment_id}"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert (
        response.json()["message"]
        == "Payment is being processed by the gateway. Please refresh in a moment."
    )

    payment.status = PaymentStatusEnum.REFUNDED
    payment.external_payment_id = "session_refunded"
    await db_session_commit.commit()

    response = await client.get(
        f"/api/v1/payments/payments/success?session_id={payment.external_payment_id}"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["message"] == (
        "Payment was declined or canceled. "
        "Please check your card balance, ensure internet limits are sufficient, "
        "or try a different payment method."
    )

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()
