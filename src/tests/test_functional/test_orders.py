import pytest
from sqlalchemy import select, delete

from models.orders import Order, OrderItem
from models.shopping_carts import Cart, CartItem


@pytest.mark.asyncio
async def test_add_movie_to_cart_create_order_check_order(authorized_client, test_movie, db_session_commit):
    """
    Test adding a movie to cart, creating an order, and verifying cart is cleared.

    Ensures that after creating an order the cart items are removed,
    the order is created with PENDING status and correct movie data.
    """
    client, user = authorized_client

    add_movie_payload = {"movie_id": test_movie.id}

    add_movie_response = await client.post("/api/v1/shopping_carts/carts", json=add_movie_payload)

    assert add_movie_response.status_code == 201
    assert add_movie_response.json()["movie"]["name"] == test_movie.name

    create_order_response = await client.post("/api/v1/orders/orders")
    assert create_order_response.status_code == 201

    create_order_response_data = create_order_response.json()
    assert "order" in create_order_response_data
    assert create_order_response_data["order"]["status"] == "pending"

    query_cart = select(Cart).where(Cart.user_id == user.id)
    result_cart = await db_session_commit.execute(query_cart)
    cart = result_cart.scalars().first()
    if cart:
        query_items = select(CartItem).where(CartItem.cart_id == cart.id)
        result_items = await db_session_commit.execute(query_items)
        remaining_items = result_items.scalars().all()
        assert remaining_items == []

    order_id = create_order_response_data["order"]["id"]
    query_order = select(Order).where(Order.id == order_id)
    result_order = await db_session_commit.execute(query_order)
    order = result_order.scalars().first()
    if order:
        await db_session_commit.execute(
            delete(OrderItem).where(OrderItem.order_id == order.id)
        )
        await db_session_commit.delete(order)
    if cart:
        await db_session_commit.delete(cart)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_order_cancel_order_check_order(authorized_client, test_movie, db_session_commit):
    """
    Test creating an order and then canceling it.

    Ensures that after canceling an order the status is updated to CANCELED
    and the correct response is returned.
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
    order_id = response_data["order"]["id"]

    response = await client.patch(f"/api/v1/orders/orders/{order_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"

    query_order = select(Order).where(Order.id == order_id)
    result_order = await db_session_commit.execute(query_order)
    order = result_order.scalars().first()
    if order:
        await db_session_commit.execute(
            delete(OrderItem).where(OrderItem.order_id == order.id)
        )
        await db_session_commit.delete(order)

    query_cart = select(Cart).where(Cart.user_id == user.id)
    result_cart = await db_session_commit.execute(query_cart)
    cart = result_cart.scalars().first()
    if cart:
        await db_session_commit.delete(cart)

    await db_session_commit.commit()
