from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from models.movies import MovieComment


@pytest.mark.asyncio
async def test_create_movie_comments_integrity_error(authorized_client, test_movie):
    """
    Test creating a movie comment when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    payload = {"text": "Test integrity error comment"}

    simulated_error = IntegrityError(statement="INSERT INTO movies ...", params={}, orig=Exception())

    with patch("routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error):
        response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/comments", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data."


@pytest.mark.asyncio
async def test_toggle_comment_reaction_integrity_error(authorized_client, test_movie, db_session_commit):
    """
    Test toggling a comment reaction when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    comment = MovieComment(
        user_id=user.id,
        movie_id=test_movie.id,
        text="Test integrity_error comment for toggle reaction"
    )
    db_session_commit.add(comment)
    await db_session_commit.commit()
    await db_session_commit.refresh(comment)

    payload = {"reaction_type": "like"}

    simulated_error = IntegrityError(statement="INSERT INTO movies ...", params={}, orig=Exception())

    with patch("routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error):
        response = await client.post(f"/api/v1/cinema/comments/{comment.id}/reactions", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data or race condition."

    await db_session_commit.delete(comment)
    await db_session_commit.commit()
