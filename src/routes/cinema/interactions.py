import math
from typing import Optional

from fastapi import APIRouter, status, Depends, HTTPException, Query
from sqlalchemy import select, func, asc, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from config.dependencies import get_current_user, get_accounts_email_notificator, get_query_params
from config.database import get_postgresql_db
from models.accounts import User
from models.movies import Movie, MovieComment, CommentReaction, MovieReaction, MovieRating, MovieFavourite, Star, \
    Director, Genre
from notifications.interfaces import EmailSenderInterface
from schemas.movies import MovieCommentResponseSchema, MovieCommentCreateSchema, CommentReactionResponse, \
    CommentReactionCreate, MovieReactionResponseSchema, MovieReactionCreateSchema, MovieRatingResponseSchema, \
    MovieRatingSchema, MovieFavouriteSchema, MovieFavouriteResponseSchema, MovieFavouriteListResponseSchema

router = APIRouter()


@router.post(
    "/movies/{movie_id}/comments",
    response_model=MovieCommentResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a movie comment or reply (Authenticated user only)",
    description=(
        "<h3>This endpoint allows authenticated users to post a new comment on an available movie "
        "or reply to an existing comment. It verifies the movie's existence and availability. "
        "If a `parent_id` is provided, it validates that the parent comment exists and belongs to the same movie. "
        "Upon successful creation, if it is a reply to another user's comment, an asynchronous email "
        "notification is triggered to notify the author of the parent comment.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to a parent comment mismatch with "
                           "the movie ID or transaction integrity failures.",
            "content": {
                "application/json": {
                    "example": {"detail": "Parent comment does not belong to this movie."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the specified movie is unavailable/missing, "
                           "or if the parent comment does not exist.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        }
    }
)
async def create_movie_comments(
    movie_id: int,
    comment_data: MovieCommentCreateSchema,
    current_user: User = Depends(get_current_user),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Publish a root comment or a nested reply under a specific movie (asynchronously).

    This function processes comment trees. It performs cascading structural validations (movie availability,
    parent-child alignment), inserts the fresh `MovieComment` record, manually overrides SQLAlchemy state anomalies
    using `set_committed_value` for eager relationship initialization (`replies`), and delegates notification delivery
    to the `EmailSenderInterface` layer if a threshold reply event is reached.

    :param movie_id: The ID of the target movie extracted from the path URL.
    :type movie_id: int
    :param comment_data: Request body payload containing the comment content and optional parent comment identifier.
    :type comment_data: MovieCommentCreateSchema
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param email_sender: The email manager instance responsible for routing system outbound alerts.
    :type email_sender: EmailSenderInterface
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A completely initialized comment response schema reflecting database attributes and user relations.
    :rtype: MovieCommentResponseSchema

    :raises HTTPException: Raises a 404 error if the movie is not active/found, or if the parent comment is missing.
    :raises HTTPException: Raises a 400 error if structural hierarchies break or data integrity checks fail on commit.
    """
    query = select(Movie).where(Movie.id == movie_id, Movie.is_available.is_(True))
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    parent_comment = None
    if hasattr(comment_data, "parent_id") and comment_data.parent_id:
        comment_query = (
            select(MovieComment)
            .options(joinedload(MovieComment.user))
            .where(MovieComment.id == comment_data.parent_id))
        comment_result = await db.execute(comment_query)
        parent_comment = comment_result.scalars().first()

        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found."
            )

        if parent_comment.movie_id != movie_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent comment does not belong to this movie."
            )

    new_comment = MovieComment(
        **comment_data.model_dump(exclude_unset=True),
        movie_id=movie_id,
        user_id=current_user.id
    )

    try:
        db.add(new_comment)
        await db.commit()
        await db.refresh(new_comment, ["user"])

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    set_committed_value(new_comment, "replies", [])

    if parent_comment and parent_comment.user_id != current_user.id:
        comments_link = f"http://127.0.0.1:8000/api/v1/cinema/movies/{movie_id}/comments"

        await email_sender.send_reply_comment_email(
            email=parent_comment.user.email,
            comment_link=comments_link
        )

    return MovieCommentResponseSchema.model_validate(new_comment)


@router.get(
    "/movies/{movie_id}/comments",
    response_model=list[MovieCommentResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get movie comments thread",
    description=(
        "<h3>This endpoint retrieves all root comments and their nested replies for a specific movie. "
        "It verifies that the target movie exists and is currently marked as available. "
        "To build the comment tree hierarchy efficiently, the query filters for top-level comments "
        "(`parent_id == None`) and recursively preloads nested replies along with the author metadata "
        "for each comment level.</h3>"
    ),
    responses={
        404: {
            "description": "Not Found if the specified movie does not exist or is marked as unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        }
    }
)
async def get_movie_comments(
    movie_id: int,
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Retrieve the structured hierarchical comment tree for a specific movie (asynchronously).

    This function coordinates the fetching of a multi-level comment thread. It validates movie availability
    first to prevent orphan reads. To eliminate massive N+1 query chains on nested recursive relations,
    it utilizes explicit `selectinload` strategy trees to batch-load root authors, direct replies,
    reply authors, and secondary sub-reply branches within minimal database round-trips.

    :param movie_id: The ID of the target movie extracted from the path URL.
    :type movie_id: int
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A list of root comment structures wrapping nested relational recursive reply blocks.
    :rtype: list[MovieCommentResponseSchema]

    :raises HTTPException: Raises a 404 error if the specified movie identifier is missing or unavailable.
    """
    movie_query = select(Movie).where(
        Movie.id == movie_id,
        Movie.is_available.is_(True)
    )
    movie_result = await db.execute(movie_query)
    movie = movie_result.scalars().first()

    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found.")

    comments_query = (
        select(MovieComment)
        .where(
            MovieComment.movie_id == movie_id,
            MovieComment.parent_id.is_(None)
        )
        .options(
            selectinload(MovieComment.user),
            selectinload(MovieComment.replies).selectinload(MovieComment.user),
            selectinload(MovieComment.replies).selectinload(MovieComment.replies)
        )
        .order_by(MovieComment.id.asc())
    )
    comments_result = await db.execute(comments_query)
    comments = comments_result.scalars().all()

    comments_list = [MovieCommentResponseSchema.model_validate(comment) for comment in comments]

    return comments_list


@router.post(
    "/comments/{comment_id}/reactions",
    response_model=Optional[CommentReactionResponse],
    status_code=status.HTTP_200_OK,
    summary="Toggle comment reaction (Authenticated user only)",
    description=(
        "<h3>This endpoint implements a flexible toggle mechanism for user reactions (e.g., like/dislike) "
        "on movie comments. It validates the target comment, its author, and the related movie. "
        "If the user submits the exact same reaction, the existing record is removed (deleted), "
        "returning a `null` payload. If the reaction type differs, it updates the state dynamically. "
        "When a brand-new reaction is successfully created, an email alert is triggered to notify "
        "the comment's author.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to runtime database anomalies, invalid reaction parameters, "
                           "or active constraint race conditions.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid input data or race condition."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the specified comment identifier cannot be resolved.",
            "content": {
                "application/json": {
                    "example": {"detail": "Comment with the given ID was not found."}
                }
            },
        }
    }
)
async def toggle_comment_reaction(
    comment_id: int,
    reaction_data: CommentReactionCreate,
    current_user: User = Depends(get_current_user),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Toggle, switch, or assign a system reaction state to a movie comment (asynchronously).

    This function handles conditional state switching for the `CommentReaction` model:
    1. Removes the entry if the reaction payload matches historical data (idempotent rollback).
    2. Overwrites the value if changing execution context (e.g., changing from Like to Dislike).
    3. Persists a new instance and dispatches an notification email to the comment owner.

    Eager loading via `joinedload` ensures immediate access to relational parent properties
    (`Comment.user` and `Comment.movie`) necessary for building outbound alert structures.

    :param comment_id: The ID of the target comment extracted from the path URL.
    :type comment_id: int
    :param reaction_data: Request body carrying the chosen reaction enum type specifier.
    :type reaction_data: CommentReactionCreate
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param email_sender: The email manager instance responsible for routing system outbound alerts.
    :type email_sender: EmailSenderInterface
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: An updated or new CommentReaction instance metadata block, or None if the reaction was toggled off.
    :rtype: CommentReactionResponse | None

    :raises HTTPException: Raises a 404 error if the targeted comment domain asset does not exist.
    :raises HTTPException: Raises a 400 error if concurrent request race conditions violate internal model constraints.
    """
    comment_query = (
        select(MovieComment)
        .where(MovieComment.id == comment_id)
        .options(
            joinedload(MovieComment.user),
            joinedload(MovieComment.movie)
        )
    )
    comment_result = await db.execute(comment_query)
    comment = comment_result.scalars().first()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment with the given ID was not found."
        )

    reaction_query = select(CommentReaction).where(
        CommentReaction.comment_id == comment_id,
        CommentReaction.user_id == current_user.id
    )
    reaction_result = await db.execute(reaction_query)
    existing_reaction = reaction_result.scalars().first()

    try:
        if existing_reaction:
            if existing_reaction.reaction_type == reaction_data.reaction_type:
                await db.delete(existing_reaction)
                await db.commit()
                return None

            else:
                existing_reaction.reaction_type = reaction_data.reaction_type
                await db.commit()
                await db.refresh(existing_reaction)
                return existing_reaction

        new_reaction = CommentReaction(
            comment_id=comment_id,
            user_id=current_user.id,
            reaction_type=reaction_data.reaction_type
        )

        db.add(new_reaction)
        await db.commit()
        await db.refresh(new_reaction)

        comments_link = f"http://127.0.0.1:8000/movies/{comment.movie.id}/comments"

        await email_sender.send_reaction_comment_email(
            email=comment.user.email,
            comment_link=comments_link
        )

        return new_reaction

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data or race condition."
        )


@router.post(
    "/movies/{movie_id}/reactions",
    response_model=Optional[MovieReactionResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Toggle movie reaction (Authenticated user only)",
    description=(
        "<h3>This endpoint implements an idempotent toggle mechanism for user reactions (like/dislike) "
        "directly on a movie. It verifies that the movie exists and is active (`is_available == True`). "
        "If the user applies the exact same reaction type, the existing record is removed (deleted) "
        "from the database, returning a `null` payload. If the reaction type differs, it updates the state. "
        "Otherwise, a brand-new reaction instance is persisted transactionally.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to database validation failures or active constraint race conditions.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid input data or race condition."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the specified movie is missing or marked as unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        }
    }
)
async def toggle_movie_reaction(
    movie_id: int,
    reaction_data: MovieReactionCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Toggle, switch, or assign a system reaction state to a specific movie asset (asynchronously).

    This function coordinates conditional branch state switches for the `MovieReaction` model:
    1. Removes the entry if the reaction payload matches historical data (idempotent removal).
    2. Overwrites the property value if changing execution context (e.g., swapping Like to Dislike).
    3. Persists a fresh instance from scratch if no relation row exists.

    It validates movie availability boundaries before processing modifications to prevent phantom entries.

    :param movie_id: The ID of the target movie extracted from the path URL.
    :type movie_id: int
    :param reaction_data: Request body payload carrying the chosen reaction enum type specifier.
    :type reaction_data: MovieReactionCreateSchema
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: An updated or new MovieReaction instance metadata block, or None if the reaction was toggled off.
    :rtype: MovieReactionResponseSchema | None

    :raises HTTPException: Raises a 404 error if the targeted movie resource does not exist or is unavailable.
    :raises HTTPException: Raises a 400 error if transaction savepoints
    trigger database constraint failures or race conditions.
    """
    movie_query = select(Movie).where(
        Movie.id == movie_id,
        Movie.is_available.is_(True)
    )
    movie_result = await db.execute(movie_query)
    movie = movie_result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    reaction_query = select(MovieReaction).where(
        MovieReaction.movie_id == movie_id,
        MovieReaction.user_id == current_user.id
    )
    reaction_result = await db.execute(reaction_query)
    existing_reaction = reaction_result.scalars().first()

    try:
        if existing_reaction:
            if existing_reaction.reaction_type == reaction_data.reaction_type:
                await db.delete(existing_reaction)
                await db.commit()
                return None

            else:
                existing_reaction.reaction_type = reaction_data.reaction_type
                await db.commit()
                await db.refresh(existing_reaction)
                return existing_reaction

        new_reaction = MovieReaction(
            movie_id=movie_id,
            user_id=current_user.id,
            reaction_type=reaction_data.reaction_type
        )
        db.add(new_reaction)
        await db.commit()
        await db.refresh(new_reaction)
        return new_reaction

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input data or race condition."
        )


@router.post(
    "/movies/{movie_id}/rate",
    response_model=MovieRatingResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Rate a movie (Authenticated user only)",
    description=(
        "<h3>This endpoint allows authenticated users to submit or update a numerical rating for a specific movie. "
        "It verifies that the movie exists and is currently active (`is_available == True`). "
        "If the user has already rated this movie, the existing score is overwritten with the new value. "
        "Otherwise, a new rating record is persisted. Both creation and modification are handled "
        "transactionally with rollback safety on database constraint failures.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request if runtime database anomalies or integrity violations occur on commit.",
            "content": {
                "application/json": {
                    "example": {"detail": "Input data is invalid."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the target movie is missing or marked as unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        }
    }
)
async def rate_movie(
    movie_id: int,
    rating_data: MovieRatingSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Submit a new rating score or update an existing one for a movie asset (asynchronously).

    This function acts as an idempotent upsert boundary for movie scores. It verifies active movie
    availability to prevent orphan relations, branches dynamically based on historical user evaluations
    (modifying an existing reference or appending a new `MovieRating` instance), and catches unexpected
    concurrency or database exceptions via an explicit `IntegrityError` rollback strategy.

    :param movie_id: The ID of the target movie extracted from the path URL.
    :type movie_id: int
    :param rating_data: Request body payload carrying the numerical evaluation score.
    :type rating_data: MovieRatingSchema
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: The newly generated or updated MovieRating record containing tracking identifiers.
    :rtype: MovieRatingResponseSchema

    :raises HTTPException: Raises a 404 error if the requested movie domain asset cannot be resolved.
    :raises HTTPException: Raises a 400 error if transaction validation steps encounter constraint errors.
    """
    movie_query = select(Movie).where(
        Movie.id == movie_id,
        Movie.is_available.is_(True)
    )
    movie_result = await db.execute(movie_query)
    movie_exists = movie_result.scalars().first()

    if not movie_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    rating_query = select(MovieRating).where(
        MovieRating.movie_id == movie_id,
        MovieRating.user_id == current_user.id
    )
    rating_result = await db.execute(rating_query)
    existing_rating = rating_result.scalars().first()

    if existing_rating:
        existing_rating.rating = rating_data.rating
        rating_obj = existing_rating

    else:

        rating_obj = MovieRating(
            rating=rating_data.rating,
            movie_id=movie_id,
            user_id=current_user.id
        )
        db.add(rating_obj)

    try:
        await db.commit()
        await db.refresh(rating_obj)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Input data is invalid."
        )

    return rating_obj


@router.post(
    "/movies/my/favorites",
    response_model=MovieFavouriteResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Add a movie to favorites (Authenticated user only)",
    description=(
        "<h3>This endpoint allows authenticated users to add a specific movie to their favorites list. "
        "It verifies that the target movie exists and is currently active (`is_available == True`). "
        "If the movie is already present in the user's favorites, the endpoint acts idempotently: "
        "it reloads the relationship data and returns the existing record without creating a duplicate. "
        "Otherwise, a new favorite association is transactionally persisted with safe rollback handling.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request if concurrent request race conditions violate model constraints on commit.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid input data."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the targeted movie is missing or marked as unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given name was not found."}
                }
            },
        }
    }
)
async def add_movie_favorites(
    movie_data: MovieFavouriteSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Append an available movie to the authenticated user's personal favorites catalog (asynchronously).

    This function serves as a safe relational link creator for the `MovieFavourite` model. It safeguards
    the system by validating movie availability first. To gracefully handle repeated requests, it applies
    an idempotent bypass branch that simply refreshes and returns historical rows. New records are appended
    safely using an atomic transaction wrapper that isolates data conflicts via `IntegrityError` tracking.

    :param movie_data: Request body payload containing the targeted movie unique identifier.
    :type movie_data: MovieFavouriteSchema
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A completely loaded and validated movie favorite record containing linked movie details.
    :rtype: MovieFavouriteResponseSchema

    :raises HTTPException: Raises a 404 error if the specified movie cannot be found or is restricted.
    :raises HTTPException: Raises a 400 error if transaction savepoints trigger input data constraint errors.
    """
    movie_query = select(Movie).where(
        Movie.id == movie_data.movie_id,
        Movie.is_available.is_(True)
    )
    movie_result = await db.execute(movie_query)
    movie = movie_result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given name was not found."
        )

    favourite_query = select(MovieFavourite).where(
        MovieFavourite.movie_id == movie_data.movie_id,
        MovieFavourite.user_id == current_user.id
    )
    favourite_result = await db.execute(favourite_query)
    existing_favourite = favourite_result.scalars().first()

    if existing_favourite:
        await db.refresh(existing_favourite, attribute_names=["movie"])
        return existing_favourite

    movie_favourite = MovieFavourite(
        movie_id=movie.id,
        user_id=current_user.id
    )

    try:
        db.add(movie_favourite)
        await db.commit()
        await db.refresh(movie_favourite, attribute_names=["movie"])

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return movie_favourite


@router.get(
    "/movies/my/favorites",
    response_model=MovieFavouriteListResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get user's favorite movies with pagination and filters",
    description=(
        "<h3>This endpoint retrieves a paginated list of available movies that the currently "
        "authenticated user has added to their favorites. It supports dynamic filtering by release year, "
        "minimum IMDb rating, and genre, alongside a comprehensive text search across movie titles, "
        "descriptions, actors (stars), and directors. Results can be sorted dynamically and include "
        "metadata for hypermedia pagination control (`prev_page`, `next_page`).</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if no matching favorite movie records are "
                           "discovered for the current page or filters.",
            "content": {
                "application/json": {
                    "example": {"detail": "No movies found."}
                }
            },
        }
    }
)
async def get_movie_favorites(
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    params: dict = Depends(get_query_params),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Fetch a filtered, sorted, and paginated stream of the user's favorite movies (asynchronously).

    This function processes complex catalog lookups by constructing two separate executable query trees:
    1. A counting sequence (`count_query`) to aggregate total matched records for pagination bounds.
    2. A data sequence (`base_query`) modified via text scanning criteria (`ilike` on many-to-many paths).

    To ensure high-performance loading and block N+1 database operations, it combined strategic `joinedload`
    for one-to-one attributes (`certification`) and `selectinload` for many-to-many collections (`genres`),
    safely cutting off execution if offset limits scale past available limits.

    :param page: Target index chunk requested by the client container.
    :type page: int
    :param per_page: Structural row limit constraint to extract per active page context.
    :type per_page: int
    :param params: Extracted dictionary containing filtering parameters (year, rating, search string, sort keys).
    :type params: dict
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A fully wrapped pagination envelope mapping rows, counters, and hypermedia trajectory strings.
    :rtype: MovieFavouriteListResponseSchema

    :raises HTTPException: Raises a 404 error if the query yields no records under the applied filters.
    """
    base_query = (
        select(MovieFavourite)
        .join(MovieFavourite.movie)
        .where(MovieFavourite.user_id == current_user.id, Movie.is_available.is_(True))
    )
    count_query = (
        select(func.count())
        .select_from(MovieFavourite)
        .join(MovieFavourite.movie)
        .where(MovieFavourite.user_id == current_user.id, Movie.is_available.is_(True))
    )

    if params["release_year"]:
        base_query = base_query.where(Movie.year == params["release_year"])
        count_query = count_query.where(Movie.year == params["release_year"])

    if params["min_rating_imdb"]:
        base_query = base_query.where(Movie.imdb >= params["min_rating_imdb"])
        count_query = count_query.where(Movie.imdb >= params["min_rating_imdb"])

    if params["genre"]:
        genre_condition = Movie.genres.any(Genre.name.ilike(f"%{params['genre']}%"))
        base_query = base_query.where(genre_condition)
        count_query = count_query.where(genre_condition)

    if params["search"]:
        search_term = f"%{params['search']}%"

        movie_text_condition = (Movie.name.ilike(search_term)) | (Movie.description.ilike(search_term))
        star_condition = Movie.stars.any(Star.name.ilike(search_term))
        director_condition = Movie.directors.any(Director.name.ilike(search_term))

        full_search_condition = movie_text_condition | star_condition | director_condition

        base_query = base_query.where(full_search_condition)
        count_query = count_query.where(full_search_condition)

    sort_mapping = {
        "id": MovieFavourite.id,
        "year": Movie.year,
        "price": Movie.price,
        "votes": Movie.votes,
    }
    sort_column = sort_mapping.get(params["sort_by"], Movie.id)

    if params["order"] == "asc":
        base_query = base_query.order_by(asc(sort_column))
    else:
        base_query = base_query.order_by(desc(sort_column))

    total_items_result = await db.execute(count_query)
    total_items = total_items_result.scalar() or 0

    total_pages = 1 if total_items == 0 else math.ceil(total_items / per_page)
    prev_page = f"/movies/my/favorites?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"/movies/my/favorites?page={page + 1}&per_page={per_page}" if page < total_pages else None

    queryset = (
        base_query
        .options(
            joinedload(MovieFavourite.movie).joinedload(Movie.certification),
            joinedload(MovieFavourite.movie).selectinload(Movie.genres))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(queryset)
    favourite_movies = result.scalars().all()

    if not favourite_movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No movies found.")

    movie_list = [MovieFavouriteResponseSchema.model_validate(movie) for movie in favourite_movies]

    return MovieFavouriteListResponseSchema(
        movies_favourite=movie_list,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.delete(
    "/movies/my/favorites/{movie_id}",
    summary="Remove a movie from favorites (Authenticated user only)",
    description=(
        "<h3>This endpoint allows authenticated users to remove a specific movie from their personal "
        "favorites list. It searches for an active relationship record matching both the provided "
        "movie ID and the current user's ID. If the movie is not found in the user's favorites, "
        "a 404 error is raised. Upon successful matching, the record is permanently deleted.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the specified movie is not present in the user's favorites list.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie is not found in your favorites."}
                }
            },
        }
    }
)
async def delete_movie_favorites(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Remove an existing movie record from the authenticated user's favorites list (asynchronously).

    This function isolates user-specific relational rows in the `MovieFavourite` link table.
    It ensures secure scoped resource deletion by strictly filtering queries with the injection context's
    `current_user.id`. If a valid tracking tuple matches, the row is scheduled for a transactional
    hard deletion via the async SQLAlchemy session block.

    :param movie_id: The ID of the target movie extracted from the path URL.
    :type movie_id: int
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A dictionary confirming successful execution of the deletion block.
    :rtype: dict

    :raises HTTPException: Raises a 404 error if no matching record ties the target movie to the current user.
    """
    query = select(MovieFavourite).where(
        MovieFavourite.movie_id == movie_id,
        MovieFavourite.user_id == current_user.id
    )
    result = await db.execute(query)
    favourite_movie = result.scalars().first()

    if not favourite_movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie is not found in your favorites."
        )

    await db.delete(favourite_movie)
    await db.commit()

    return {"detail": "Favourite Movie deleted successfully."}
