from unittest.mock import patch

import pytest
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from models.shopping_carts import CartItem, Cart


@pytest.mark.asyncio
async def test_add_movie_to_cart_integrity_error(authorized_client, test_movie, db_session_commit):
    """
    Test adding a movie to cart when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    payload = {"movie_id": test_movie.id}

    simulated_error = IntegrityError(statement="INSERT INTO movies ...", params={}, orig=Exception())

    with patch("routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error):
        response = await client.post("/api/v1/shopping_carts/carts", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "This movie is already in your cart."

    query = select(Cart).where(Cart.user_id == user.id)
    result = await db_session_commit.execute(query)
    cart = result.scalars().first()
    if cart:
        await db_session_commit.execute(
            delete(CartItem).where(CartItem.cart_id == cart.id)
        )
        await db_session_commit.delete(cart)
        await db_session_commit.commit()
