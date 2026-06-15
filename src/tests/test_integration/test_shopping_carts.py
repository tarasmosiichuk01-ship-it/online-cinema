from decimal import Decimal

import pytest
from sqlalchemy import delete

from models.orders import OrderStatusEnum, Order, OrderItem
from models.shopping_carts import CartItem


@pytest.mark.asyncio
async def test_add_movie_to_cart_unauthorized_user(client, test_movie):

    payload = {"movie_id": test_movie.id}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "You must sign up or log in before completing a purchase. Register here: http://127.0.0.1:8000/api/v1/accounts/register/"


@pytest.mark.asyncio
async def test_add_movie_to_cart_if_movie_not_found(authorized_client):

    client, user = authorized_client

    payload = {"movie_id": 999999999}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_add_movie_to_cart_if_movie_is_purchased(authorized_client, test_movie, db_session_commit):

    client, user = authorized_client

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PAID
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    order_item = OrderItem(
        order_id=order.id,
        movie_id=test_movie.id,
        price_at_order=Decimal("299.99")
    )
    db_session_commit.add(order_item)
    await db_session_commit.commit()

    payload = {"movie_id": test_movie.id}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Repeat purchases are not allowed."

    await db_session_commit.execute(delete(CartItem).where(CartItem.movie_id == test_movie.id))

    await db_session_commit.delete(order_item)
    await db_session_commit.delete(order)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_add_movie_to_cart_success(authorized_client, test_movie):
    client, user = authorized_client

    payload = {"movie_id": test_movie.id}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 201
    response_data = response.json()
    assert response_data["movie"]["name"] == test_movie.name

