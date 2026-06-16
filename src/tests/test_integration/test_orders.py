import pytest
from sqlalchemy import delete

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

