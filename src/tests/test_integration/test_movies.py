import pytest


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


