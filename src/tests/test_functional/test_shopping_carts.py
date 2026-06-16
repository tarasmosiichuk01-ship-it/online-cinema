import pytest
from sqlalchemy import select

from models.shopping_carts import Cart


@pytest.mark.asyncio
async def test_add_movie_to_cart_get_carts_delete_movie_from_cart_check_cart(authorized_client, test_movie, db_session_commit):
    """
    Test full cart lifecycle: add movie, get cart, delete movie, verify empty cart.

    Ensures that a user can add a movie to their cart, retrieve the cart
    with correct data, delete the movie from the cart, and verify
    that the cart is empty afterwards.
    """
    client, user = authorized_client

    add_movie_payload = {"movie_id": test_movie.id}

    add_movie_response = await client.post("/api/v1/shopping_carts/carts", json=add_movie_payload)

    assert add_movie_response.status_code == 201
    add_movie_response_data = add_movie_response.json()
    assert add_movie_response_data["movie"]["name"] == test_movie.name

    get_cart_items_response = await client.get("/api/v1/shopping_carts/carts")

    assert get_cart_items_response.status_code == 200
    assert get_cart_items_response.json()["cart_items"][0]["movie"]["name"] == test_movie.name

    deleted_item_response = await client.delete(f"/api/v1/shopping_carts/carts/items/{test_movie.id}")
    assert deleted_item_response.status_code == 204

    get_cart_response = await client.get("/api/v1/shopping_carts/carts")

    assert get_cart_response.status_code == 200
    assert get_cart_response.json()["cart_items"] == []

    query = select(Cart).where(Cart.user_id == user.id)
    result = await db_session_commit.execute(query)
    cart = result.scalars().first()
    if cart:
        await db_session_commit.delete(cart)
        await db_session_commit.commit()
