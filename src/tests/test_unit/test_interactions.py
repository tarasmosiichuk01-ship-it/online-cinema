from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError


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
