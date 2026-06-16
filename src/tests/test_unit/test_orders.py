from unittest.mock import patch

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from models.shopping_carts import Cart, CartItem


@pytest.mark.asyncio
async def test_create_order_integrity_error(authorized_client, test_movie, db_session_commit):
    """
    Test creating an order when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(cart_id=cart.id, movie_id=test_movie.id)
    db_session_commit.add(cart_item)
    await db_session_commit.commit()

    simulated_error = IntegrityError(statement="INSERT INTO movies ...", params={}, orig=Exception())

    with patch("routes.orders.AsyncSession.commit", side_effect=simulated_error):
        response = await client.post("/api/v1/orders/orders")

    assert response.status_code == 400
    assert response.json()["detail"] == "An error occurred while creating the order."

    await db_session_commit.rollback()
    query = select(Cart).where(Cart.user_id == user.id)
    result = await db_session_commit.execute(query)
    cart = result.scalars().first()
    if cart:
        await db_session_commit.execute(
            delete(CartItem).where(CartItem.cart_id == cart.id)
        )
        await db_session_commit.delete(cart)
        await db_session_commit.commit()
