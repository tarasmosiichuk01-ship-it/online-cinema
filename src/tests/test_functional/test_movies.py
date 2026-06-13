import pytest
from sqlalchemy import select

from models.movies import Movie


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
