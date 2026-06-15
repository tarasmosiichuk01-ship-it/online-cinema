from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from models.orders import OrderStatusEnum, Order, OrderItem
from models.shopping_carts import CartItem, Cart


@pytest.mark.asyncio
async def test_add_movie_to_cart_unauthorized_user(client, test_movie):
    """
    Test adding a movie to cart by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message with a registration link when an unauthenticated user
    attempts to add a movie to the cart.
    """
    payload = {"movie_id": test_movie.id}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "You must sign up or log in before completing a purchase. Register here: http://127.0.0.1:8000/api/v1/accounts/register/"


@pytest.mark.asyncio
async def test_add_movie_to_cart_if_movie_not_found(authorized_client):
    """
    Test adding a non-existent movie to the cart.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the movie with the given ID does not exist.
    """
    client, user = authorized_client

    payload = {"movie_id": 999999999}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_add_movie_to_cart_if_movie_is_purchased(authorized_client, test_movie, db_session_commit):
    """
    Test adding a movie to cart that has already been purchased.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the user attempts to add a movie they have
    already purchased.
    """
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
async def test_add_movie_to_cart_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful addition of a movie to the cart.

    Ensures that the endpoint returns a 201 status code and the correct
    cart item data when an authorized user adds a movie to their cart.
    """
    client, user = authorized_client

    payload = {"movie_id": test_movie.id}

    response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 201
    response_data = response.json()
    assert response_data["movie"]["name"] == test_movie.name

    await db_session_commit.execute(
        delete(CartItem).where(CartItem.movie_id == test_movie.id)
    )
    await db_session_commit.flush()

    query = select(Cart).where(Cart.user_id == user.id)
    result = await db_session_commit.execute(query)
    cart = result.scalars().first()
    if cart:
        await db_session_commit.delete(cart)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_current_user_cart_unauthorized_user(client):
    """
    Test getting the current user's cart by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to get their cart.
    """
    response = await client.get("/api/v1/shopping_carts/carts")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

