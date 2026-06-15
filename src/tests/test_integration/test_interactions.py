import pytest
from sqlalchemy import select

from models.movies import Movie, Certification, MovieComment, MovieReaction, CommentReaction, ReactionTypeEnum, \
    MovieRating


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


@pytest.mark.asyncio
async def test_create_movie_comments_when_parents_comment_belongs_to_another_movie(
    authorized_client,
    test_movie,
    db_session_commit
):
    """
    Test creating a comment with a parent comment that belongs to another movie.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the parent comment belongs to a different movie.
    """
    client, user = authorized_client

    certification = Certification(name="PG-comment-test")
    db_session_commit.add(certification)
    await db_session_commit.flush()

    movie = Movie(
        name="Movie To Comment",
        year=2021,
        time=60,
        imdb=6.9,
        votes=587,
        description="This movie for comments.",
        price=4.36,
        certification_id=certification.id
    )
    db_session_commit.add(movie)
    await db_session_commit.commit()
    await db_session_commit.refresh(movie)

    test_movie_payload = {"text": "Test comment"}

    test_movie_response = await client.post(
        f"/api/v1/cinema/movies/{test_movie.id}/comments",
        json=test_movie_payload
    )
    assert test_movie_response.status_code == 201
    test_movie_comment_id = test_movie_response.json()["id"]

    movie_payload = {"text": "Test comment fo test movie", "parent_id": test_movie_comment_id}

    movie_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments",
        json=movie_payload
    )

    assert movie_response.status_code == 400
    assert movie_response.json()["detail"] == "Parent comment does not belong to this movie."

    query_comment = select(MovieComment).where(MovieComment.movie_id == test_movie.id)
    result_comment = await db_session_commit.execute(query_comment)
    comment = result_comment.scalars().first()
    if comment:
        await db_session_commit.delete(comment)
        await db_session_commit.flush()

    await db_session_commit.delete(movie)
    await db_session_commit.delete(certification)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_create_movie_comments_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful comment creation for a movie.

    Ensures that the endpoint returns a 201 status code and the correct
    response data when an authorized user creates a comment for a movie.
    """
    client, user = authorized_client

    payload = {"text": "Test comment success"}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/comments", json=payload)
    assert response.status_code == 201

    response_data = response.json()
    comment_id = response_data["id"]
    assert response_data["text"] == payload["text"]
    assert "id" in response_data
    assert response_data["user"] == user.email
    assert response_data["replies"] == []

    query = select(MovieComment).where(MovieComment.id == comment_id)
    result = await db_session_commit.execute(query)
    comment = result.scalars().first()
    if comment:
        await db_session_commit.delete(comment)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_get_movie_comments_if_movie_not_found(authorized_client):
    """
    Test getting comments for a non-existent movie.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the movie with the given ID does not exist.
    """
    client, user = authorized_client

    response = await client.get("/api/v1/cinema/movies/99999/comments")
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie not found."


@pytest.mark.asyncio
async def test_get_movie_comments_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful retrieval of comments for a movie.

    Ensures that the endpoint returns a 200 status code and a list
    of comments when a valid movie ID is provided.
    """
    client, user = authorized_client

    payload = {"text": "Test comment for get"}
    create_response = await client.post(
        f"/api/v1/cinema/movies/{test_movie.id}/comments",
        json=payload
    )
    assert create_response.status_code == 201
    comment_id = create_response.json()["id"]

    response = await client.get(f"/api/v1/cinema/movies/{test_movie.id}/comments")
    assert response.status_code == 200

    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) > 0
    assert response_data[0]["text"] == payload["text"]
    assert response_data[0]["replies"] == []

    query = select(MovieComment).where(MovieComment.id == comment_id)
    result = await db_session_commit.execute(query)
    comment = result.scalars().first()
    if comment:
        await db_session_commit.delete(comment)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_comment_reaction_if_comment_not_found(authorized_client):
    """
    Test toggling a reaction on a non-existent comment.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the comment with the given ID does not exist.
    """
    client, user = authorized_client

    payload = {"reaction_type": "like"}

    response = await client.post("/api/v1/cinema/comments/999999/reactions", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Comment with the given ID was not found."


@pytest.mark.asyncio
async def test_toggle_comment_reaction_unauthorized_user(client):
    """
    Test toggling a comment reaction by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to toggle a reaction.
    """
    payload = {"reaction_type": "like"}

    response = await client.post("/api/v1/cinema/comments/999999/reactions", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_toggle_comment_reaction_with_repeated_reaction(authorized_client, test_movie, db_session_commit):
    """
    Test toggling a comment reaction when the same reaction already exists.

    Ensures that the endpoint returns a 200 status code and None
    when the user toggles the same reaction type, effectively removing it.
    """
    client, user = authorized_client

    comment = MovieComment(
        user_id=user.id,
        movie_id=test_movie.id,
        text="Test comment for toggle reaction"
    )
    db_session_commit.add(comment)
    await db_session_commit.flush()

    existing_reaction = CommentReaction(
        user_id=user.id,
        comment_id=comment.id,
        reaction_type=ReactionTypeEnum.LIKE
    )
    db_session_commit.add(existing_reaction)
    await db_session_commit.commit()

    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/comments/{comment.id}/reactions", json=payload)
    assert response.status_code == 200
    assert response.json() is None

    await db_session_commit.delete(comment)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_comment_reaction_with_another_reaction(authorized_client, test_movie, db_session_commit):
    """
    Test toggling a comment reaction when a different reaction already exists.

    Ensures that the endpoint returns a 200 status code and updates
    the reaction type when the user toggles a different reaction.
    """
    client, user = authorized_client

    comment = MovieComment(
        user_id=user.id,
        movie_id=test_movie.id,
        text="Test comment for toggle reaction"
    )
    db_session_commit.add(comment)
    await db_session_commit.flush()

    existing_reaction = CommentReaction(
        user_id=user.id,
        comment_id=comment.id,
        reaction_type=ReactionTypeEnum.DISLIKE
    )
    db_session_commit.add(existing_reaction)
    await db_session_commit.commit()

    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/comments/{comment.id}/reactions", json=payload)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["reaction_type"] == "like"
    assert response_data["comment_id"] == comment.id

    query_reaction = select(CommentReaction).where(
        CommentReaction.comment_id == comment.id,
        CommentReaction.user_id == user.id
    )
    result_reaction = await db_session_commit.execute(query_reaction)
    reaction = result_reaction.scalars().first()
    if reaction:
        await db_session_commit.delete(reaction)
        await db_session_commit.flush()

    await db_session_commit.delete(comment)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_comment_reaction_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful creation of a new comment reaction.

    Ensures that the endpoint returns a 200 status code and the correct
    reaction data when an authorized user adds a reaction to a comment
    for the first time.
    """
    client, user = authorized_client

    comment = MovieComment(
        user_id=user.id,
        movie_id=test_movie.id,
        text="Test comment for toggle reaction"
    )
    db_session_commit.add(comment)
    await db_session_commit.commit()
    await db_session_commit.refresh(comment)

    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/comments/{comment.id}/reactions", json=payload)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["reaction_type"] == "like"
    assert response_data["comment_id"] == comment.id

    query_reaction = select(CommentReaction).where(
        CommentReaction.comment_id == comment.id,
        CommentReaction.user_id == user.id
    )
    result_reaction = await db_session_commit.execute(query_reaction)
    reaction = result_reaction.scalars().first()
    if reaction:
        await db_session_commit.delete(reaction)
        await db_session_commit.flush()

    await db_session_commit.delete(comment)
    await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_movie_reaction_unauthorized_user(client, test_movie):
    """
    Test toggling a movie reaction by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to toggle a reaction.
    """
    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/reactions", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_toggle_movie_reaction_if_movie_not_found(authorized_client):
    """
    Test toggling a movie reaction when the movie does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the movie with the given ID does not exist.
    """
    client, user = authorized_client

    payload = {"reaction_type": "like"}

    response = await client.post("/api/v1/cinema/movies/999999999/reactions", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."



@pytest.mark.asyncio
async def test_toggle_movie_reaction_with_repeated_reaction(authorized_client, test_movie, db_session_commit):
    """
    Test toggling a movie reaction when the same reaction already exists.

    Ensures that the endpoint returns a 200 status code and None
    when the user toggles the same reaction type, effectively removing it.
    """
    client, user = authorized_client

    existing_reaction = MovieReaction(
        user_id=user.id,
        movie_id=test_movie.id,
        reaction_type=ReactionTypeEnum.LIKE
    )
    db_session_commit.add(existing_reaction)
    await db_session_commit.commit()

    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/reactions", json=payload)
    assert response.status_code == 200
    assert response.json() is None

    query = select(MovieReaction).where(MovieReaction.id == existing_reaction.id)
    result = await db_session_commit.execute(query)
    reaction = result.scalars().first()
    if reaction:
        await db_session_commit.delete(reaction)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_movie_reaction_with_another_reaction(authorized_client, test_movie, db_session_commit):
    """
    Test toggling a movie reaction when a different reaction already exists.

    Ensures that the endpoint returns a 200 status code and updates
    the reaction type when the user toggles a different reaction.
    """
    client, user = authorized_client

    existing_reaction = MovieReaction(
        user_id=user.id,
        movie_id=test_movie.id,
        reaction_type=ReactionTypeEnum.DISLIKE
    )
    db_session_commit.add(existing_reaction)
    await db_session_commit.commit()

    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/reactions", json=payload)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["reaction_type"] == "like"
    assert response_data["movie_id"] == test_movie.id

    query = select(MovieReaction).where(MovieReaction.id == existing_reaction.id)
    result = await db_session_commit.execute(query)
    reaction = result.scalars().first()
    if reaction:
        await db_session_commit.delete(reaction)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_toggle_movie_reaction_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful creation of a new movie reaction.

    Ensures that the endpoint returns a 200 status code and the correct
    reaction data when an authorized user adds a reaction to a movie
    for the first time.
    """
    client, user = authorized_client

    payload = {"reaction_type": "like"}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/reactions", json=payload)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["reaction_type"] == "like"
    assert response_data["movie_id"] == test_movie.id

    query = select(MovieReaction).where(
        MovieReaction.movie_id == test_movie.id,
        MovieReaction.user_id == user.id
    )
    result = await db_session_commit.execute(query)
    reaction = result.scalars().first()
    if reaction:
        await db_session_commit.delete(reaction)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_rate_movie_unauthorized_user(client, test_movie):
    """
    Test rating a movie by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to rate a movie.
    """
    payload = {"rating": 10}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/rate", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_rate_movie_if_movie_not_found(authorized_client):
    """
    Test rating a movie that does not exist.

    Ensures that the endpoint returns a 404 status code and an appropriate
    error message when the movie with the given ID does not exist.
    """
    client, user = authorized_client

    payload = {"rating": 10}

    response = await client.post("/api/v1/cinema/movies/999999999/rate", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie with the given ID was not found."


@pytest.mark.asyncio
async def test_rate_movie_with_existing_rating(authorized_client, test_movie, db_session_commit):
    """
    Test rating a movie when a rating already exists.

    Ensures that the endpoint returns a 200 status code and updates
    the existing rating when the user rates the same movie again.
    """
    client, user = authorized_client

    existing_rating = MovieRating(
        user_id=user.id,
        movie_id=test_movie.id,
        rating=5
    )
    db_session_commit.add(existing_rating)
    await db_session_commit.commit()

    payload = {"rating": 10}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/rate", json=payload)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["rating"] == 10

    query = select(MovieRating).where(
        MovieRating.movie_id == test_movie.id,
        MovieRating.user_id == user.id
    )
    result = await db_session_commit.execute(query)
    rating = result.scalars().first()
    if rating:
        await db_session_commit.delete(rating)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_rate_movie_success(authorized_client, test_movie, db_session_commit):
    """
    Test successful movie rating.

    Ensures that the endpoint returns a 200 status code and the correct
    rating data when an authorized user rates a movie for the first time.
    """
    client, user = authorized_client

    payload = {"rating": 10}

    response = await client.post(f"/api/v1/cinema/movies/{test_movie.id}/rate", json=payload)
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["rating"] == 10

    query = select(MovieRating).where(
        MovieRating.movie_id == test_movie.id,
        MovieRating.user_id == user.id
    )
    result = await db_session_commit.execute(query)
    rating = result.scalars().first()
    if rating:
        await db_session_commit.delete(rating)
        await db_session_commit.commit()


@pytest.mark.asyncio
async def test_add_movie_favorites_unauthorized_user(client, test_movie):
    """
    Test adding a movie to favorites by an unauthorized user.

    Ensures that the endpoint returns a 401 status code and an appropriate
    error message when an unauthenticated user attempts to add a movie
    to favorites.
    """
    payload = {"movie_id": test_movie.id}

    response = await client.post("/api/v1/cinema/movies/my/favorites", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

