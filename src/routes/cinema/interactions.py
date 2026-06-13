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


# Authorization endpoint
@router.post(
    "/movies/{movie_id}/comments",
    response_model=MovieCommentResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_movie_comments(
    movie_id: int,
    comment_data: MovieCommentCreateSchema,
    current_user: User = Depends(get_current_user),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
    db: AsyncSession = Depends(get_postgresql_db)
):

    query = select(Movie).where(Movie.id == movie_id, Movie.is_available == True)
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


# Authorization endpoint
@router.get("/movies/{movie_id}/comments")
async def get_movie_comments(
    movie_id: int,
    db: AsyncSession = Depends(get_postgresql_db)
):
    movie_query = select(Movie).where(
        Movie.id == movie_id,
        Movie.is_available == True
    )
    movie_result = await db.execute(movie_query)
    movie = movie_result.scalars().first()

    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found.")


    comments_query = (
        select(MovieComment)
        .where(
            MovieComment.movie_id == movie_id,
            MovieComment.parent_id == None
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


# Authorization endpoint

@router.post(
    "/comments/{comment_id}/reactions",
    response_model=Optional[CommentReactionResponse],
    status_code=status.HTTP_200_OK
)
async def toggle_comment_reaction(
    comment_id: int,
    reaction_data: CommentReactionCreate,
    current_user: User = Depends(get_current_user),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
    db: AsyncSession = Depends(get_postgresql_db)
):
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

        comments_link = f"http://127.0.0.1/movies/{comment.movie.id}/comments"

        await email_sender.send_reaction_comment_email(
            email=comment.user.email,
            comment_link=comments_link
        )

        return new_reaction

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data or race condition.")


# Authorization endpoint
@router.post(
    "/movies/{movie_id}/reactions",
    response_model=Optional[MovieReactionResponseSchema],
    status_code=status.HTTP_200_OK
)
async def toggle_movie_reaction(
    movie_id: int,
    reaction_data: MovieReactionCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    movie_query = select(Movie).where(
        Movie.id == movie_id,
        Movie.is_available == True
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data or race condition.")


# Authorization endpoint
@router.post(
    "/movies/{movie_id}/rate",
    response_model=MovieRatingResponseSchema,
    status_code=status.HTTP_200_OK
)
async def rate_movie(
    movie_id: int,
    rating_data: MovieRatingSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    movie_query = select(Movie).where(
        Movie.id == movie_id,
        Movie.is_available == True
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


# Authorization endpoint
@router.post("/movies/my/favorites",
    response_model=MovieFavouriteResponseSchema,
    status_code=status.HTTP_200_OK
)
async def add_movie_favorites(
    movie_data: MovieFavouriteSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    movie_query = select(Movie).where(
        Movie.id == movie_data.movie_id,
        Movie.is_available == True
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


# Authorization endpoint
@router.get(
    "/movies/my/favorites",
    response_model=MovieFavouriteListResponseSchema,
    status_code=status.HTTP_200_OK
)
async def get_movie_favorites(
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    params: dict = Depends(get_query_params),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):


    base_query = (
        select(MovieFavourite)
        .join(MovieFavourite.movie)
        .where(MovieFavourite.user_id == current_user.id, Movie.is_available == True)
    )
    count_query = (
        select(func.count())
        .select_from(MovieFavourite)
        .join(MovieFavourite.movie)
        .where(MovieFavourite.user_id == current_user.id, Movie.is_available == True)
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


# Authorization endpoint
@router.delete(
    "/movies/my/favorites/{movie_id}",
    status_code=status.HTTP_200_OK
)
async def delete_movie_favorites(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
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
