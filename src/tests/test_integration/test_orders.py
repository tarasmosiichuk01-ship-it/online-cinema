import pytest
from sqlalchemy import delete, select

from models.orders import OrderStatusEnum, Order, OrderItem
from models.shopping_carts import Cart, CartItem


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


@pytest.mark.asyncio
async def test_create_order_if_carts_is_empty(authorized_client):
    """
    Test creating an order when the cart is empty.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the user attempts to create an order with an empty cart.
    """
    client, user = authorized_client

    response = await client.post("/api/v1/orders/orders")

    assert response.status_code == 400
    assert response.json()["detail"] == "Your cart is empty"


@pytest.mark.asyncio
async def test_create_order_with_unavailable_movie(authorized_client, test_movie, db_session_commit):
    """
    Test creating an order when all movies in the cart are unavailable.

    Ensures that the endpoint returns a 400 status code, an appropriate
    error message, and warnings about unavailable movies when all movies
    in the cart are currently unavailable.
    """
    client, user = authorized_client

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(cart_id=cart.id, movie_id=test_movie.id)
    db_session_commit.add(cart_item)

    test_movie.is_available = False
    await db_session_commit.commit()

    response = await client.post("/api/v1/orders/orders")

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "All movies in your cart are currently unavailable."
    assert len(response.json()["detail"]["warnings"]) > 0
    assert any(test_movie.name in warning for warning in response.json()["detail"]["warnings"])

    test_movie.is_available = True
    await db_session_commit.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    await db_session_commit.delete(cart)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_order_if_movie_is_bought(authorized_client, test_movie, db_session_commit):
    """
    Test creating an order when all movies in the cart have already been purchased.

    Ensures that the endpoint returns a 400 status code and warnings
    indicating that the movies were already purchased and excluded from the order.
    """
    client, user = authorized_client

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(cart_id=cart.id, movie_id=test_movie.id)
    db_session_commit.add(cart_item)
    await db_session_commit.flush()

    order = Order(user_id=user.id, status=OrderStatusEnum.PAID)
    db_session_commit.add(order)
    await db_session_commit.flush()

    order_item = OrderItem(
        order_id=order.id,
        movie_id=test_movie.id,
        price_at_order=test_movie.price
    )
    db_session_commit.add(order_item)
    await db_session_commit.commit()

    response = await client.post("/api/v1/orders/orders")

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "All movies in your cart are currently unavailable."
    assert len(response.json()["detail"]["warnings"]) > 0
    assert any(test_movie.name in warning for warning in response.json()["detail"]["warnings"])

    await db_session_commit.delete(order_item)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    await db_session_commit.delete(cart)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_order_if_is_already_pending_order(authorized_client, test_movie, db_session_commit):
    """
    Test creating an order when there is already a pending order with the same movies.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the user already has a pending order containing
    some of the movies from their cart.
    """
    client, user = authorized_client

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(cart_id=cart.id, movie_id=test_movie.id)
    db_session_commit.add(cart_item)
    await db_session_commit.flush()

    order = Order(user_id=user.id, status=OrderStatusEnum.PENDING)
    db_session_commit.add(order)
    await db_session_commit.flush()

    order_item = OrderItem(
        order_id=order.id,
        movie_id=test_movie.id,
        price_at_order=test_movie.price
    )
    db_session_commit.add(order_item)
    await db_session_commit.commit()

    response = await client.post("/api/v1/orders/orders")

    assert response.status_code == 400
    assert response.json()["detail"] == "You already have a pending order containing some of these movies. Please complete or cancel it first."

    await db_session_commit.delete(order_item)
    await db_session_commit.flush()
    await db_session_commit.delete(order)
    await db_session_commit.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    await db_session_commit.delete(cart)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_order_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful order creation.

    Ensures that the endpoint returns a 201 status code, the order is created
    in the database with PENDING status, and cart items are removed after
    the order is created.
    """
    client, user = authorized_client

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(cart_id=cart.id, movie_id=test_movie.id)
    db_session_commit.add(cart_item)
    await db_session_commit.commit()

    response = await client.post("/api/v1/orders/orders")
    assert response.status_code == 201

    response_data = response.json()
    assert "order" in response_data
    assert response_data["order"]["status"] == "pending"

    query_order = select(Order).where(Order.user_id == user.id)
    result_order = await db_session_commit.execute(query_order)
    created_order = result_order.scalars().first()
    assert created_order is not None
    assert created_order.status == OrderStatusEnum.PENDING

    query_cart_item = select(CartItem).where(CartItem.cart_id == cart.id)
    result_cart_item = await db_session_commit.execute(query_cart_item)
    remaining_items = result_cart_item.scalars().all()
    assert remaining_items == []

    query_order_items = select(OrderItem).where(OrderItem.order_id == created_order.id)
    result_order_items = await db_session_commit.execute(query_order_items)
    order_items = result_order_items.scalars().all()
    for item in order_items:
        await db_session_commit.delete(item)
    await db_session_commit.flush()

    await db_session_commit.delete(created_order)
    await db_session_commit.delete(cart)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_orders_unauthorized_user(client):
    """
    Test getting orders by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to get their orders.
    """
    response = await client.get("/api/v1/orders/orders")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_get_orders_if_orders_is_empty(authorized_client):
    """
    Test getting orders when the user has no orders.

    Ensures that the endpoint returns a 200 status code and an empty
    list when the user has not created any orders.
    """
    client, user = authorized_client

    response = await client.get("/api/v1/orders/orders")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_orders_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful retrieval of orders.

    Ensures that the endpoint returns a 200 status code and a list
    of orders with correct order items data.
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

    response = await client.get("/api/v1/orders/orders")

    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) > 0
    assert response_data[0]["order_items"][0]["movie"]["name"] == test_movie.name

    await db_session_commit.rollback()

    query_items = select(OrderItem).where(OrderItem.order_id == order.id)
    result_items = await db_session_commit.execute(query_items)
    items = result_items.scalars().all()
    for item in items:
        await db_session_commit.delete(item)
    await db_session_commit.flush()

    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_cancel_order_unauthorized_user(client):
    """
    Test canceling an order by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to cancel an order.
    """
    response = await client.patch("/api/v1/orders/orders/1/cancel")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_cancel_order_if_order_not_found(authorized_client):
    """
    Test canceling an order that does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no order with the given ID exists for the current user.
    """
    client, user = authorized_client

    response = await client.patch("/api/v1/orders/orders/9999999/cancel")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.asyncio
async def test_cancel_order_if_order_is_not_pending(authorized_client, test_movie, db_session_commit):
    """
    Test canceling an order that is not in PENDING status.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the user attempts to cancel an order that is
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

    response = await client.patch(f"/api/v1/orders/orders/{order.id}/cancel")

    assert response.status_code == 400
    assert response.json()["detail"] == "You can only cancel pending orders"

    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_cancel_order_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful order cancellation.

    Ensures that the endpoint returns a 200 status code and the order
    status is updated to CANCELED in the response.
    """
    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=test_movie.price,
    )
    db_session_commit.add(order)
    await db_session_commit.commit()

    response = await client.patch(f"/api/v1/orders/orders/{order.id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"

    await db_session_commit.refresh(order)
    await db_session_commit.delete(order)
    await db_session_commit.commit()

