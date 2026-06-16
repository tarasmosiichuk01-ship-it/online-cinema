import pytest
from sqlalchemy import select

from models.movies import Movie, Certification
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


@pytest.mark.asyncio
async def test_add_movies_to_cart_clear_cart_check_empty(authorized_client, test_movie, db_session_commit):
    """
    Test adding multiple movies to cart, clearing the cart, and verifying it is empty.

    Ensures that a user can add multiple movies to their cart, clear the cart,
    and verify that all items are removed afterwards.
    """
    client, user = authorized_client

    certification = Certification(name="PG-clear-cart-test")
    db_session_commit.add(certification)
    await db_session_commit.flush()

    second_movie = Movie(
        name="Second Movie For Cart Test",
        year=2015,
        time=100,
        imdb=7.0,
        votes=500,
        description="Second movie description",
        price=8.99,
        certification_id=certification.id,
    )
    db_session_commit.add(second_movie)
    await db_session_commit.commit()
    await db_session_commit.refresh(second_movie)

    first_response = await client.post(
        "/api/v1/shopping_carts/carts",
        json={"movie_id": test_movie.id}
    )
    assert first_response.status_code == 201

    second_response = await client.post(
        "/api/v1/shopping_carts/carts",
        json={"movie_id": second_movie.id}
    )
    assert second_response.status_code == 201

    get_response = await client.get("/api/v1/shopping_carts/carts")
    assert get_response.status_code == 200
    assert len(get_response.json()["cart_items"]) == 2

    clear_response = await client.delete("/api/v1/shopping_carts/carts/clear")
    assert clear_response.status_code == 204

    get_after_clear = await client.get("/api/v1/shopping_carts/carts")
    assert get_after_clear.status_code == 200
    assert get_after_clear.json()["cart_items"] == []

    query = select(Cart).where(Cart.user_id == user.id)
    result = await db_session_commit.execute(query)
    cart = result.scalars().first()
    if cart:
        await db_session_commit.delete(cart)
    await db_session_commit.delete(second_movie)
    await db_session_commit.delete(certification)
    await db_session_commit.commit()
