import pytest
from sqlalchemy import select, delete

from models.movies import Movie, MovieComment, Certification


@pytest.mark.asyncio
async def test_create_movie_comment_and_reply_comment(authorized_client, db_session_commit):
    """
    Test creating a comment and replying to it.

    Ensures that a reply comment is correctly linked to its parent comment
    through the parent_id field.
    """
    certification = Certification(name="AG-comment-reply-test")
    db_session_commit.add(certification)
    await db_session_commit.flush()

    movie = Movie(
        name="Test New Movie123",
        year=2011,
        time=198,
        imdb=7.6,
        votes=190,
        description="Test description123",
        price=5.93,
        certification_id=certification.id,
    )
    db_session_commit.add(movie)
    await db_session_commit.commit()
    await db_session_commit.refresh(movie)

    client, user = authorized_client

    parent_comment_payload = {"text": "Test comment success"}
    parent_comment_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments",
        json=parent_comment_payload
    )
    assert parent_comment_response.status_code == 201
    parent_comment_id = parent_comment_response.json()["id"]

    reply_comment_payload = {"text": "Test reply comment", "parent_id": parent_comment_id}
    reply_comment_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments",
        json=reply_comment_payload
    )
    assert reply_comment_response.status_code == 201

    reply_data = reply_comment_response.json()
    assert "parent_id" in reply_data
    assert reply_data["parent_id"] == parent_comment_id

    await db_session_commit.execute(
        delete(MovieComment).where(MovieComment.movie_id == movie.id)
    )
    await db_session_commit.flush()
    await db_session_commit.delete(movie)
    await db_session_commit.delete(certification)
    await db_session_commit.commit()

