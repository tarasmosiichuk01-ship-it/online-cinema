import pytest


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
    assert response.json()["message"] == "You have canceled the payment. Your order remains pending."



