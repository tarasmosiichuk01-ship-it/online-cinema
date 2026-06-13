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

    response = await client.post("/api/v1/cinema/movies/1234567/comments", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_create_movie_comments_unauthorized_user(client, test_movie):
    """
    Test creating a comment by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to create a comment.
    """
    payload = {"text": "Test comment"}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/comments", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_create_movie_comments_if_parent_comment_not_found(authorized_client, test_movie):
    """
    Test creating a comment with a non-existent parent comment.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the parent comment with the given ID does not exist.
    """
    client, user = authorized_client

    payload = {"text": "Test comment", "parent_id": 99999}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/comments", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Parent comment not found."

