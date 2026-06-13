from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models.movies import Movie, Genre


@pytest.mark.asyncio
async def test_create_movie_if_existing_movie_is(test_movie, moderator_client, db_session_commit):
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
async def test_create_movie_not_moderator(test_movie, authorized_client, db_session_commit):
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
    assert response.json()["detail"] == "Access forbidden. Moderator or Admin role required."


@pytest.mark.asyncio
async def test_create_movie_integrity_error(test_movie, moderator_client, db_session_commit):
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

    simulated_error = IntegrityError(statement="INSERT INTO movies ...", params={}, orig=Exception())

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
    response = await client.get("/api/v1/cinema/movies?page=1&per_page=10&sort_by=id&order=desc")
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
    response = await client.get(f"/api/v1/cinema/movies?min_rating_imdb={test_movie.imdb}")
    assert response.status_code == 200

    response_data = response.json()
    assert len(response_data["movies"]) > 0


