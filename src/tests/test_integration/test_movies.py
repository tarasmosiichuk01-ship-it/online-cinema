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


