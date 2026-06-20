from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models.accounts import UserGroup, UserGroupEnum, User
from models.movies import Movie, Genre, Certification
from models.orders import Order, OrderStatusEnum, OrderItem
from models.shopping_carts import Cart, CartItem


@pytest.mark.asyncio
async def test_create_movie_if_existing_movie_is(
    test_movie, moderator_client, db_session_commit
):
    """
    Test creating a movie that already exists.

    Ensures that the endpoint returns a 409 status code when a movie
    with the same name, year and time already exists in the database.
    """

    payload = {
        "name": test_movie.name,
        "year": test_movie.year,
        "time": test_movie.time,
        "imdb": 7.5,
        "votes": 1000,
        "description": "Test description",
        "price": 9.99,
        "certification": "PG-12",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    response = await moderator_client.post("/api/v1/cinema/movies", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"A movie with the name '{test_movie.name}' and release year '{test_movie.year}' already exists."
    )


@pytest.mark.asyncio
async def test_create_movie_unauthorized_user(test_movie, client, db_session_commit):
    """
    Test creating a movie by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to create a movie.
    """
    payload = {
        "name": "Super New Movie",
        "year": test_movie.year,
        "time": test_movie.time,
        "imdb": 7.5,
        "votes": 190,
        "description": "Test description",
        "price": 9.93,
        "certification": "PG-22",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    response = await client.post("/api/v1/cinema/movies", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_create_movie_not_moderator(
    test_movie, authorized_client, db_session_commit
):
    """
    Test creating a movie by a user without moderator/admin privileges.

    Ensures that the endpoint returns a 403 Forbidden status code and the
    appropriate error message when an ordinary authorized user attempts
    to create a movie record.

    Args:
        test_movie: Fixture providing a saved test movie instance.
        authorized_client: The asynchronous HTTP client fixture authorized as a regular user.
        db_session_commit: The asynchronous database session fixture.
    """
    client, user = authorized_client
    payload = {
        "name": test_movie.name,
        "year": test_movie.year,
        "time": test_movie.time,
        "imdb": 7.5,
        "votes": 990,
        "description": "Test description",
        "price": 9.92,
        "certification": "PG-12",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    response = await client.post("/api/v1/cinema/movies", json=payload)
    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Access forbidden. Moderator or Admin role required."
    )


@pytest.mark.asyncio
async def test_create_movie_integrity_error(
    test_movie, moderator_client, db_session_commit
):
    """
    Test creating a movie when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    payload = {
        "name": "Super New Movie",
        "year": test_movie.year,
        "time": test_movie.time,
        "imdb": 7.5,
        "votes": 190,
        "description": "Test description",
        "price": 9.93,
        "certification": "PG-22",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch("routes.cinema.movies.AsyncSession.commit", side_effect=simulated_error):
        response = await moderator_client.post("/api/v1/cinema/movies", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data."


@pytest.mark.asyncio
async def test_create_movie_success(test_movie, moderator_client, db_session_commit):
    """
    Test successful movie creation by a moderator.

    Ensures that the endpoint returns a 201 status code, the correct response
    data, and that the movie is actually saved in the database.
    """
    payload = {
        "name": "Super New Movie",
        "year": test_movie.year,
        "time": test_movie.time,
        "imdb": 7.5,
        "votes": 190,
        "description": "Test description",
        "price": 9.93,
        "certification": "PG-22",
        "genres": [],
        "stars": [],
        "directors": [],
    }

    response = await moderator_client.post("/api/v1/cinema/movies", json=payload)
    assert response.status_code == 201

    response_data = response.json()
    assert response_data["name"] == payload["name"]
    assert response_data["year"] == payload["year"]
    assert response_data["price"] == str(payload["price"])
    assert "id" in response_data

    query = select(Movie).where(Movie.name == payload["name"])
    result = await db_session_commit.execute(query)
    created_movie = result.scalars().first()
    assert created_movie is not None, "Movie was not created in the database."
    assert created_movie.name == payload["name"]

    if created_movie:
        await db_session_commit.delete(created_movie)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_movie_list_if_not_movies(client):
    """
    Test getting movie list when no movies are available.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when there are no available movies in the database.
    """
    response = await client.get("/api/v1/cinema/movies")
    assert response.status_code == 404
    assert response.json()["detail"] == "No movies found."


@pytest.mark.asyncio
async def test_get_movie_list_with_pagination_and_sorting(test_movie, client):
    """
    Test getting movie list with pagination and sorting parameters.

    Ensures that the endpoint returns a 200 status code and correct
    pagination fields when valid pagination and sorting parameters are provided.
    """
    response = await client.get(
        "/api/v1/cinema/movies?page=1&per_page=10&sort_by=id&order=desc"
    )
    assert response.status_code == 200

    response_data = response.json()
    assert "movies" in response_data
    assert "total_items" in response_data
    assert "total_pages" in response_data
    assert "prev_page" in response_data
    assert "next_page" in response_data
    assert response_data["prev_page"] is None
    assert len(response_data["movies"]) > 0


@pytest.mark.asyncio
async def test_get_movie_list_filter_by_release_year(client, test_movie):
    """
    Test filtering movie list by release year.

    Ensures that the endpoint returns only movies matching the specified release year.
    """
    response = await client.get(f"/api/v1/cinema/movies?release_year={test_movie.year}")
    assert response.status_code == 200

    response_data = response.json()
    assert all(movie["year"] == test_movie.year for movie in response_data["movies"])


@pytest.mark.asyncio
async def test_get_movie_list_filter_by_min_rating_imdb(client, test_movie):
    """
    Test filtering movie list by minimum IMDB rating.

    Ensures that the endpoint returns a 200 status code and at least one movie
    when filtering by the minimum IMDB rating of the test movie.
    """
    response = await client.get(
        f"/api/v1/cinema/movies?min_rating_imdb={test_movie.imdb}"
    )
    assert response.status_code == 200

    response_data = response.json()
    assert len(response_data["movies"]) > 0


@pytest.mark.asyncio
async def test_get_movie_list_filter_by_search(client, test_movie):
    """
    Test filtering movie list by search term.

    Ensures that the endpoint returns only movies matching the search term
    in name, description, stars, or directors.
    """
    response = await client.get(f"/api/v1/cinema/movies?search={test_movie.name}")
    assert response.status_code == 200

    response_data = response.json()
    assert len(response_data["movies"]) > 0
    assert any(movie["name"] == test_movie.name for movie in response_data["movies"])


@pytest.mark.asyncio
async def test_get_movie_list_filter_by_genre(client, test_movie, db_session_commit):
    """
    Test filtering movie list by genre.

    Ensures that the endpoint returns only movies belonging to the specified genre.
    """
    genre = Genre(name="Test Genre")
    db_session_commit.add(genre)
    await db_session_commit.flush()

    query = (
        select(Movie)
        .options(selectinload(Movie.genres))
        .where(Movie.id == test_movie.id)
    )
    result = await db_session_commit.execute(query)
    movie = result.scalars().first()

    movie.genres.append(genre)
    await db_session_commit.commit()

    response = await client.get("/api/v1/cinema/movies?genre=Test Genre")
    assert response.status_code == 200

    response_data = response.json()
    assert len(response_data["movies"]) > 0

    movie.genres.remove(genre)
    await db_session_commit.delete(genre)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_movie_list_success(test_movie, client):
    """
    Test successful retrieval of movie list.

    Ensures that the endpoint returns a 200 status code and correct
    response structure with all required pagination fields.
    """
    response = await client.get("/api/v1/cinema/movies")
    assert response.status_code == 200

    response_data = response.json()
    assert "movies" in response_data
    assert "total_items" in response_data
    assert "total_pages" in response_data
    assert "prev_page" in response_data
    assert "next_page" in response_data
    assert len(response_data["movies"]) > 0
    assert response_data["total_items"] > 0
    assert response_data["prev_page"] is None


@pytest.mark.asyncio
async def test_get_movie_by_id_if_not_movie(client):
    """
    Test getting a movie by ID when the movie does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no movie with the given ID exists in the database.
    """
    response = await client.get("/api/v1/cinema/movies/99999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_get_movie_by_id_if_movie_not_available(
    client, test_movie, db_session_commit
):
    """
    Test getting a movie by ID when the movie is not available.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the movie exists but is marked as unavailable.
    """
    test_movie.is_available = False
    await db_session_commit.commit()

    response = await client.get(f"/api/v1/cinema/movies/{test_movie.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."

    test_movie.is_available = True
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_movie_by_id_success(client, test_movie):
    """
    Test successful retrieval of a movie by ID.

    Ensures that the endpoint returns a 200 status code and the correct
    response structure with all required fields.
    """
    response = await client.get(f"/api/v1/cinema/movies/{test_movie.id}")
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["name"] == test_movie.name
    assert response_data["year"] == test_movie.year
    assert response_data["description"] == test_movie.description
    assert response_data["price"] == str(test_movie.price)


@pytest.mark.asyncio
async def test_update_movie_if_not_movie(moderator_client):
    """
    Test updating a movie that does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no movie with the given ID exists in the database.
    """
    payload = {
        "name": "New Movie Test",
        "year": 2011,
        "description": "Movie Test Test Movie",
    }

    response = await moderator_client.patch(
        f"/api/v1/cinema/movies/9999999", json=payload
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_update_movie_not_moderator(authorized_client, test_movie):
    """
    Test updating a movie by a user without moderator privileges.

    Ensures that the endpoint returns a 403 status code and an appropriate
    error message when a regular authorized user attempts to update a movie.
    """
    client, user = authorized_client

    payload = {
        "name": "New Movie Test",
        "year": 2011,
        "description": "Movie Test Test Movie",
    }

    response = await client.patch(
        f"/api/v1/cinema/movies/{test_movie.id}", json=payload
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Access forbidden. Moderator or Admin role required."
    )


@pytest.mark.asyncio
async def test_update_movie_integrity_error(moderator_client, test_movie):
    """
    Test updating a movie when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    payload = {
        "name": "New Movie Test",
        "year": 2011,
        "description": "Movie Test Test Movie",
    }

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch("routes.cinema.movies.AsyncSession.commit", side_effect=simulated_error):
        response = await moderator_client.patch(
            f"/api/v1/cinema/movies/{test_movie.id}", json=payload
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data."


@pytest.mark.asyncio
async def test_update_movie_success(moderator_client, test_movie):
    """
    Test successful movie update by a moderator.

    Ensures that the endpoint returns a 200 status code and the updated
    movie data in the response.
    """
    payload = {
        "name": "New Movie Test",
        "year": 2011,
        "description": "Movie Test Test Movie",
    }

    response = await moderator_client.patch(
        f"/api/v1/cinema/movies/{test_movie.id}", json=payload
    )

    assert response.status_code == 200
    response_data = response.json()

    assert response_data["name"] == payload["name"]
    assert response_data["year"] == payload["year"]
    assert response_data["description"] == payload["description"]


@pytest.mark.asyncio
async def test_delete_movie_if_not_movie(moderator_client):
    """
    Test deleting a movie that does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when no movie with the given ID exists in the database.
    """
    response = await moderator_client.delete(f"/api/v1/cinema/movies/9999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_delete_movie_not_moderator(authorized_client, test_movie):
    """
    Test deleting a movie by a user without moderator privileges.

    Ensures that the endpoint returns a 403 status code and an appropriate
    error message when a regular authorized user attempts to delete a movie.
    """
    client, user = authorized_client

    response = await client.delete(f"/api/v1/cinema/movies/{test_movie.id}")

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Access forbidden. Moderator or Admin role required."
    )


@pytest.mark.asyncio
async def test_delete_movie_if_movie_in_cart(
    moderator_client, test_movie, db_session_commit, seed_user_groups
):
    """
    Test deleting a movie that is currently in a user's shopping cart.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the movie cannot be deleted because it exists in
    at least one user's cart.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session_commit.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="cart_user@example.com", raw_password="Test1234!", group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    cart = Cart(user_id=user.id)
    db_session_commit.add(cart)
    await db_session_commit.flush()

    cart_item = CartItem(cart_id=cart.id, movie_id=test_movie.id)
    db_session_commit.add(cart_item)
    await db_session_commit.commit()

    response = await moderator_client.delete(f"/api/v1/cinema/movies/{test_movie.id}")
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Warning to Moderator: This movie cannot be deleted because it is currently in users' shopping carts."
    )

    await db_session_commit.delete(cart_item)
    await db_session_commit.delete(cart)
    await db_session_commit.delete(user)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_delete_movie_if_movie_is_purchased(
    moderator_client, test_movie, db_session_commit, seed_user_groups
):
    """
    Test deleting a movie that has already been purchased by a user.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the movie cannot be deleted because it has already
    been purchased by at least one user.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session_commit.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="purchased_user@example.com",
        raw_password="Test1234!",
        group_id=user_group.id,
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    order = Order(
        user_id=user.id, status=OrderStatusEnum.PAID, total_amount=test_movie.price
    )
    db_session_commit.add(order)
    await db_session_commit.flush()

    order_item = OrderItem(
        order_id=order.id, movie_id=test_movie.id, price_at_order=test_movie.price
    )
    db_session_commit.add(order_item)
    await db_session_commit.commit()

    response = await moderator_client.delete(f"/api/v1/cinema/movies/{test_movie.id}")
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "This movie cannot be deleted because it has already been purchased by at least one user."
    )

    await db_session_commit.delete(order_item)
    await db_session_commit.delete(order)
    await db_session_commit.delete(user)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_delete_movie_success(moderator_client, db_session_commit):
    """
    Test successful movie deletion by a moderator.

    Ensures that the endpoint returns a 200 status code and a success message
    when a valid movie ID is provided and the movie is not in any cart or order.
    """
    certification = Certification(name="PG-delete-test")
    db_session_commit.add(certification)
    await db_session_commit.flush()

    movie = Movie(
        name="Movie To Delete",
        year=2020,
        time=90,
        imdb=6.0,
        votes=500,
        description="This movie will be deleted.",
        price=4.99,
        certification_id=certification.id,
    )
    db_session_commit.add(movie)
    await db_session_commit.commit()
    await db_session_commit.refresh(movie)

    movie_id = movie.id

    response = await moderator_client.delete(f"/api/v1/cinema/movies/{movie_id}")

    assert response.status_code == 200
    assert response.json()["detail"] == "Movie deleted successfully."

    query = select(Movie).where(Movie.id == movie_id)
    result = await db_session_commit.execute(query)
    deleted_movie = result.scalars().first()
    assert deleted_movie is None, "Movie should be deleted from the database."

    await db_session_commit.delete(certification)
    await db_session_commit.commit()
