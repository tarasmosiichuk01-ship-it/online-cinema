from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.movies import MovieComment, MovieReaction, MovieRating, MovieFavourite


@pytest.mark.asyncio
async def test_create_movie_comments_integrity_error(authorized_client, test_movie):
    """
    Test creating a movie comment when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    payload = {"text": "Test integrity error comment"}

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch(
        "routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error
    ):
        response = await client.post(
            f"/api/v1/cinema/movies/{test_movie.id}/comments", json=payload
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data."


@pytest.mark.asyncio
async def test_toggle_comment_reaction_integrity_error(
    authorized_client, test_movie, db_session_commit
):
    """
    Test toggling a comment reaction when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    comment = MovieComment(
        user_id=user.id,
        movie_id=test_movie.id,
        text="Test integrity_error comment for toggle reaction",
    )
    db_session_commit.add(comment)
    await db_session_commit.commit()
    await db_session_commit.refresh(comment)

    payload = {"reaction_type": "like"}

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch(
        "routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error
    ):
        response = await client.post(
            f"/api/v1/cinema/comments/{comment.id}/reactions", json=payload
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data or race condition."

    await db_session_commit.delete(comment)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_movie_reaction_integrity_error(
    authorized_client, test_movie, db_session_commit
):
    """
    Test toggling a movie reaction when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    payload = {"reaction_type": "like"}

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch(
        "routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error
    ):
        response = await client.post(
            f"/api/v1/cinema/movies/{test_movie.id}/reactions", json=payload
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data or race condition."

    query = select(MovieReaction).where(
        MovieReaction.movie_id == test_movie.id, MovieReaction.user_id == user.id
    )
    result = await db_session_commit.execute(query)
    reaction = result.scalars().first()
    if reaction:
        await db_session_commit.delete(reaction)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_rate_movie_integrity_error(
    authorized_client, test_movie, db_session_commit
):
    """
    Test rating a movie when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    payload = {"rating": 10}

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch(
        "routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error
    ):
        response = await client.post(
            f"/api/v1/cinema/movies/{test_movie.id}/rate", json=payload
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Input data is invalid."

    query = select(MovieRating).where(
        MovieRating.movie_id == test_movie.id, MovieRating.user_id == user.id
    )
    result = await db_session_commit.execute(query)
    rating = result.scalars().first()
    if rating:
        await db_session_commit.delete(rating)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_add_movie_favorites_integrity_error(
    authorized_client, test_movie, db_session_commit
):
    """
    Test adding a movie to favorites when a database integrity error occurs.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when an IntegrityError is raised during the commit operation.
    """
    client, user = authorized_client

    payload = {"movie_id": test_movie.id}

    simulated_error = IntegrityError(
        statement="INSERT INTO movies ...", params={}, orig=Exception()
    )

    with patch(
        "routes.cinema.interactions.AsyncSession.commit", side_effect=simulated_error
    ):
        response = await client.post("/api/v1/cinema/movies/my/favorites", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid input data."

    query = select(MovieFavourite).where(
        MovieFavourite.movie_id == test_movie.id, MovieFavourite.user_id == user.id
    )
    result = await db_session_commit.execute(query)
    favorite = result.scalars().first()
    if favorite:
        await db_session_commit.delete(favorite)
        await db_session_commit.commit()
