from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.movies import Movie


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

