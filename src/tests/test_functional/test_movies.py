import pytest
from sqlalchemy import select

from models.accounts import User, UserGroup, UserGroupEnum
from models.movies import Movie
from models.orders import Order, OrderStatusEnum, OrderItem
from models.shopping_carts import Cart, CartItem


@pytest.mark.asyncio
async def test_create_get_update_delete_movie(moderator_client, db_session_commit):
    """
    Test full CRUD lifecycle for a movie.

    Ensures that a moderator can create a movie, retrieve it by ID,
    update its details, and delete it — verifying database state at each step.
    """
    create_payload = {
        "name": "Functional Test Movie",
        "year": 1999,
        "time": 95,
        "imdb": 8.5,
        "votes": 290,
        "description": "Functional test description",
        "price": 9.83,
        "certification": "PG-12",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    create_response = await moderator_client.post("/api/v1/cinema/movies", json=create_payload)
    create_response_data = create_response.json()
    assert create_response.status_code == 201
    assert create_response_data["name"] == create_payload["name"]
    assert create_response_data["year"] == create_payload["year"]
    assert create_response_data["price"] == str(create_payload["price"])
    assert "id" in create_response_data

    query = select(Movie).where(Movie.name == create_payload["name"])
    result = await db_session_commit.execute(query)
    created_movie = result.scalars().first()
    assert created_movie is not None, "Movie was not created in the database."
    assert created_movie.name == create_payload["name"]

    get_response = await moderator_client.get(f"/api/v1/cinema/movies/{created_movie.id}")
    assert get_response.status_code == 200

    get_response_data = get_response.json()
    assert get_response_data["name"] == create_payload["name"]
    assert get_response_data["year"] == create_payload["year"]
    assert get_response_data["description"] == create_payload["description"]
    assert get_response_data["price"] == str(create_payload["price"])

    update_payload = {
        "name": "New Movie Test",
        "year": 2011,
        "description": "Movie Test Test Movie",
    }

    update_response = await moderator_client.patch(f"/api/v1/cinema/movies/{created_movie.id}", json=update_payload)

    assert update_response.status_code == 200
    update_response_data = update_response.json()

    assert update_response_data["name"] == update_payload["name"]
    assert update_response_data["year"] == update_payload["year"]
    assert update_response_data["description"] == update_payload["description"]

    delete_response = await moderator_client.delete(f"/api/v1/cinema/movies/{created_movie.id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["detail"] == "Movie deleted successfully."

    query = select(Movie).where(Movie.id == created_movie.id)
    result = await db_session_commit.execute(query)
    deleted_movie = result.scalars().first()
    assert deleted_movie is None, "Movie should be deleted from the database."


@pytest.mark.asyncio
async def test_create_add_to_cart_and_try_delete_movie(
    moderator_client,
    db_session_commit,
    seed_user_groups
):
    """
    Test that a movie cannot be deleted when it is in a user's shopping cart.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when attempting to delete a movie that exists in a cart.
    """
    create_payload = {
        "name": "Interesting Movie",
        "year": 2010,
        "time": 112,
        "imdb": 6.5,
        "votes": 112,
        "description": "Movie description",
        "price": 7.83,
        "certification": "PG-19",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    create_response = await moderator_client.post("/api/v1/cinema/movies", json=create_payload)
    create_response_data = create_response.json()
    assert create_response.status_code == 201
    movie_id = create_response_data["id"]

    query_user = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result_user = await db_session_commit.execute(query_user)
    user_group = result_user.scalars().first()

    user = User.create(
        email="testuser1234@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(
        cart_id=cart.id,
        movie_id=movie_id,
    )
    db_session_commit.add(cart_item)
    await db_session_commit.commit()

    delete_response = await moderator_client.delete(f"/api/v1/cinema/movies/{movie_id}")
    assert delete_response.status_code == 400
    assert delete_response.json()["detail"] == "Warning to Moderator: This movie cannot be deleted because it is currently in users' shopping carts."

    await db_session_commit.delete(cart_item)
    await db_session_commit.delete(cart)
    await db_session_commit.delete(user)
    query_movie = select(Movie).where(Movie.id == movie_id)
    result_movie = await db_session_commit.execute(query_movie)
    movie = result_movie.scalars().first()
    if movie:
        await db_session_commit.delete(movie)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_buy_and_try_delete_movie(moderator_client, db_session_commit, seed_user_groups):
    """
    Test that a movie cannot be deleted after it has been purchased.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when attempting to delete a movie that has already been
    purchased by at least one user.
    """
    create_payload = {
        "name": "Bought Movie",
        "year": 2015,
        "time": 162,
        "imdb": 7.9,
        "votes": 198,
        "description": "Bought Movie description",
        "price": 5.83,
        "certification": "PG-91",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    create_response = await moderator_client.post("/api/v1/cinema/movies", json=create_payload)
    create_response_data = create_response.json()
    assert create_response.status_code == 201
    movie_id = create_response_data["id"]

    query_user = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result_user = await db_session_commit.execute(query_user)
    user_group = result_user.scalars().first()

    user = User.create(
        email="testuser1234@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    order = Order(
        user_id=user.id,
        status=OrderStatusEnum.PAID,
        total_amount=create_payload["price"],
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    order_item = OrderItem(
        order_id=order.id,
        movie_id=movie_id,
        price_at_order=create_payload["price"],
    )
    db_session_commit.add(order_item)
    await db_session_commit.commit()

    delete_response = await moderator_client.delete(f"/api/v1/cinema/movies/{movie_id}")
    assert delete_response.status_code == 400
    assert delete_response.json()["detail"] == (
        "This movie cannot be deleted because it has already been purchased by at least one user."
    )

    await db_session_commit.delete(order_item)
    await db_session_commit.delete(order)
    await db_session_commit.delete(user)
    query_movie = select(Movie).where(Movie.id == movie_id)
    result_movie = await db_session_commit.execute(query_movie)
    movie = result_movie.scalars().first()
    if movie:
        await db_session_commit.delete(movie)
    await db_session_commit.commit()
