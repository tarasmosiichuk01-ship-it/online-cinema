import pytest
from sqlalchemy import select

from models.accounts import UserGroupEnum, UserGroup, User
from models.orders import Order, OrderStatusEnum, OrderItem
from models.payments import Payment, PaymentStatusEnum


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


@pytest.mark.asyncio
async def test_get_payments_success_if_payment_not_found(authorized_client):
    """
    Test getting payment success page when payment does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no payment with the given session ID exists
    for the current user.
    """
    client, user = authorized_client

    response = await client.get(
        "/api/v1/payments/payments/success?session_id=999999999999999"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Payment not found."


@pytest.mark.asyncio
async def test_get_payments_success_with_pending_status(authorized_client, test_movie, db_session_commit):
    """
    Test getting payment success page when payment is in PENDING status.

    Ensures that the endpoint returns a 200 status code and a processing
    message when the payment is still being processed by the gateway.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status=PaymentStatusEnum.PENDING,
        amount=test_movie.price,
        external_payment_id="test_session_id",
        payment_intent_id="test_intent_id",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    response = await client.get(
        f"/api/v1/payments/payments/success?session_id={payment.external_payment_id}"
    )

    assert response.status_code == 200

    assert response.json()["status"] == "processing"
    assert response.json()["message"] == "Payment is being processed by the gateway. Please refresh in a moment."
    assert response.json()["payment_status"] == "PENDING"

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_payments_success_with_successful_status(authorized_client, test_movie, db_session_commit):
    """
    Test getting payment success page when payment is in SUCCESSFUL status.

    Ensures that the endpoint returns a 200 status code and a success
    message when the payment has been successfully processed.
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

    response = await client.get(
        f"/api/v1/payments/payments/success?session_id={payment.external_payment_id}"
    )

    assert response.status_code == 200

    assert response.json()["status"] == "success"
    assert response.json()["message"] == "Thank you for your purchase!"
    assert response.json()["payment_status"] == "SUCCESSFUL"

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_payments_success_with_another_status(authorized_client, test_movie, db_session_commit):
    """
    Test getting payment success page when payment is in a failed/refunded status.

    Ensures that the endpoint returns a 200 status code and a failure
    message when the payment was declined, canceled or refunded.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.CANCELED,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status=PaymentStatusEnum.REFUNDED,
        amount=test_movie.price,
        external_payment_id="test_session_id",
        payment_intent_id="test_intent_id",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    response = await client.get(
        f"/api/v1/payments/payments/success?session_id={payment.external_payment_id}"
    )

    assert response.status_code == 200

    assert response.json()["status"] == "failed"
    assert response.json()["message"] == "Payment was declined or canceled. Please check your card balance, ensure internet limits are sufficient, or try a different payment method."
    assert response.json()["payment_status"] == "REFUNDED"

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_payments_canceled_with_success_status(client):
    """
    Test getting payment canceled page.

    Ensures that the endpoint returns a 200 status code and an appropriate
    message when the user cancels the payment process.
    """
    response = await client.get("/api/v1/payments/payments/canceled")

    assert response.status_code == 200

    assert response.json()["status"] == "canceled"
    assert response.json()["message"] == "You have canceled the payment. Your order remains pending."


@pytest.mark.asyncio
async def test_get_payments_unauthorized_user(client):
    """
    Test getting payments by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to get
    their payment history.
    """
    response = await client.get("/api/v1/payments/payments/my")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_get_payments_if_not_payments(authorized_client):
    """
    Test getting payments when the user has no payment history.

    Ensures that the endpoint returns a 200 status code and an empty
    list when the user has not made any payments.
    """
    client, user = authorized_client

    response = await client.get("/api/v1/payments/payments/my")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_payments_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful retrieval of payment history.

    Ensures that the endpoint returns a 200 status code and a list
    of payments with correct structure when the user has payments.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status=PaymentStatusEnum.PENDING,
        amount=test_movie.price,
        external_payment_id="test_session_id",
        payment_intent_id="test_intent_id",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    response = await client.get("/api/v1/payments/payments/my")

    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) > 0
    assert "id" in response_data[0]
    assert "status" in response_data[0]
    assert "amount" in response_data[0]

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_payments_for_admin_unauthorized_user(client):
    """
    Test getting payments for admin by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to access
    the admin payments endpoint.
    """
    response = await client.get("/api/v1/payments/admin/payments")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_get_payments_for_admin_not_admin(authorized_client):
    """
    Test getting payments for admin by a non-admin user.

    Ensures that the endpoint returns a 403 status code and an appropriate
    error message when a regular authorized user attempts to access
    the admin payments endpoint.
    """
    client, user = authorized_client

    response = await client.get("/api/v1/payments/admin/payments")

    assert response.status_code == 403
    assert response.json()["detail"] == "Access forbidden. Admin role required."


@pytest.mark.asyncio
async def test_get_payments_for_admin_success(admin_client, test_movie, db_session_commit):
    """
    Test successful retrieval of payments for admin.

    Ensures that the endpoint returns a 200 status code and a list
    of payments with correct structure when accessed by an admin user.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session_commit.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="payment_test_user@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status=PaymentStatusEnum.PENDING,
        amount=test_movie.price,
        external_payment_id="test_session_id",
        payment_intent_id="test_intent_id",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    response = await admin_client.get("/api/v1/payments/admin/payments")

    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) > 0
    assert "id" in response_data[0]
    assert "status" in response_data[0]
    assert "amount" in response_data[0]

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.delete(user)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_payments_for_admin_with_filters(admin_client, test_movie, db_session_commit, seed_user_groups):
    """
    Test getting payments for admin with various filter parameters.

    Ensures that the endpoint returns a 200 status code and correctly
    filters payments by user_id, start_date, end_date and payment_status.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session_commit.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="payment_filter_test_user@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status=PaymentStatusEnum.PENDING,
        amount=test_movie.price,
        external_payment_id="test_filter_session_id",
        payment_intent_id="test_filter_intent_id",
    )
    db_session_commit.add(payment)
    await db_session_commit.commit()

    response = await admin_client.get(f"/api/v1/payments/admin/payments?user_id={user.id}")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) > 0
    assert response.json()[0]["order_id"] == order.id

    response = await admin_client.get(
        "/api/v1/payments/admin/payments?start_date=2010-01-01&end_date=2030-12-31"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = await admin_client.get(
        "/api/v1/payments/admin/payments?payment_status=PENDING"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert all(p["status"] == "PENDING" for p in response.json())

    await db_session_commit.delete(payment)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.delete(user)
    await db_session_commit.commit()

