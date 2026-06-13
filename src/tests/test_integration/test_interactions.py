import pytest


@pytest.mark.asyncio
async def test_create_movie_comments_if_movie_not_found(authorized_client):
    """
    Test creating a comment for a non-existent movie.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the movie with the given ID does not exist.
    """
    client, user = authorized_client

    payload = {"text": "Test comment"}

    response = await client.post(f"/api/v1/cinema/movies/1234567/comments", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."