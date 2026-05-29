import math

from fastapi import APIRouter, status, Query, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from config.dependencies import get_moderator_user, get_current_user
from database import get_postgresql_db
from models.accounts import User, UserGroupEnum
from models.movies import Movie, Genre, Certification, Star, Director, MovieComment, MovieReaction, MovieRating, \
    MovieFavourite
from schemas.movies import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema, \
    GenreListResponseSchema, GenreDetailSchema, GenreCreateShema, MovieCreateSchema, MovieUpdateSchema, \
    MovieCommentCreateSchema, MovieCommentResponseSchema, GenreUpdateShema, StarCreateSchema, StarResponseSchema, \
    StarListResponseSchema, StarUpdateSchema, DirectorCreateSchema, DirectorResponseSchema, DirectorListResponseSchema, \
    DirectorUpdateSchema, MovieReactionResponseSchema, MovieReactionCreateSchema, MovieRatingResponseSchema, \
    MovieRatingSchema, MovieFavouriteResponseSchema, MovieFavouriteSchema
from utils.utils import get_or_create, resolve_movie_relations

router = APIRouter()

# Moderators endpoint
@router.post(
    "/movies",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_movie(
    movie_data: MovieCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    existing_query = select(Movie).where(
        (Movie.name == movie_data.name),
        (Movie.year == movie_data.year),
        (Movie.time == movie_data.time)
    )
    existing_result = await db.execute(existing_query)
    existing_movie = existing_result.scalars().first()

    if existing_movie:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A movie with the name '{movie_data.name}' and release year "
                f"'{movie_data.year}' already exists."
            )
        )

    genres, stars, directors, certification = await resolve_movie_relations(
        db=db,
        genres=movie_data.genres,
        stars=movie_data.stars,
        directors=movie_data.directors,
        certification=movie_data.certification,
    )

    try:
        new_movie = Movie(
            name=movie_data.name,
            year=movie_data.year,
            time=movie_data.time,
            imdb=movie_data.imdb,
            votes=movie_data.votes,
            meta_score=movie_data.meta_score,
            gross=movie_data.gross,
            description=movie_data.description,
            price=movie_data.price,
            certification=certification,
            genres=genres,
            stars=stars,
            directors=directors
        )

        db.add(new_movie)
        await db.commit()
        await db.refresh(new_movie, ["certification", "genres", "stars", "directors"])

        return MovieDetailSchema.model_validate(new_movie)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")



# Public endpoint
@router.get(
    "/movies",
    response_model=MovieListResponseSchema
)
async def get_movie_list(
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    db: AsyncSession = Depends(get_postgresql_db)
) -> MovieListResponseSchema:

    total_items = (await db.execute(select(func.count()).select_from(Movie))).scalar()
    total_pages = 1 if total_items == 0 else math.ceil(total_items / per_page)
    prev_page = f"/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"/movies/?page={page + 1}&per_page={per_page}" if page < total_pages else None

    queryset = (
        select(Movie).order_by(Movie.id.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    result = await db.execute(queryset)
    movies = result.scalars().all()

    if not movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No movies found.")

    movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]

    return MovieListResponseSchema(
        movies=movie_list,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


# Public endpoint
@router.get(
    "/movies/{movie_id}",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_200_OK
)
async def get_movie_by_id(movie_id: int, db: AsyncSession = Depends(get_postgresql_db)):
    query = (
        select(Movie)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
        )
        .where(Movie.id == movie_id)
    )
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    return MovieDetailSchema.model_validate(movie)


# Moderators endpoint
@router.patch("/movies/{movie_id}", status_code=status.HTTP_200_OK)
async def update_movie(
    movie_id: int,
    movie_data: MovieUpdateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    update_dict = movie_data.model_dump(exclude_unset=True)

    genres, stars, directors, certification = await resolve_movie_relations(
        db=db,
        genres=update_dict.get("genres"),
        stars=update_dict.get("stars"),
        directors=update_dict.get("directors"),
        certification=update_dict.get("certification")
    )

    if genres is not None: movie.genres = genres
    if stars is not None: movie.stars = stars
    if directors is not None: movie.directors = directors
    if certification is not None: movie.certification = certification

    movie_fields = {"genres", "stars", "directors", "certification"}
    for field, value in update_dict.items():
        if field not in movie_fields:
            setattr(movie, field, value)

    try:
        await db.commit()
        await db.refresh(movie)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return {"detail": "Movie updated successfully."}



# Moderators endpoint
@router.delete("/movies/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_movie(
    movie_id: int,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    await db.delete(movie)
    await db.commit()

    return {"detail": "Movie deleted successfully."}


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
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    new_comment = MovieComment(
        **comment_data.model_dump(exclude_unset=True),
        movie_id=movie_id,
        user_id=current_user.id
    )
    try:
        db.add(new_comment)
        await db.commit()
        await db.refresh(new_comment)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return new_comment


# Authorization endpoint
@router.get("/movies/{movie_id}/comments")
async def get_movie_comments(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(MovieComment).where(MovieComment.movie_id == movie_id).options(joinedload(MovieComment.user))
    result = await db.execute(query)
    comments = result.scalars().all()

    comments_list = [MovieCommentResponseSchema.model_validate(comment) for comment in comments]

    return comments_list





# Authorization endpoint
@router.post(
    "/movies/{movie_id}/like",
    response_model=MovieReactionResponseSchema,
    status_code=status.HTTP_200_OK
)
async def like_movie(
    movie_id: int,
    reaction_data: MovieReactionCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    new_like = MovieReaction(
        **reaction_data.model_dump(exclude_unset=True),
        movie_id=movie_id,
        user_id=current_user.id
    )

    try:
        db.add(new_like)
        await db.commit()
        await db.refresh(new_like)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return new_like


# Authorization endpoint
@router.post(
    "/movies/{movie_id}/dislike",
    response_model=MovieReactionResponseSchema,
    status_code=status.HTTP_200_OK
)
async def dislike_movie(
    movie_id: int,
    reaction_data: MovieReactionCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    new_dislike = MovieReaction(
        **reaction_data.model_dump(exclude_unset=True),
        movie_id=movie_id,
        user_id=current_user.id
    )

    try:
        db.add(new_dislike)
        await db.commit()
        await db.refresh(new_dislike)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return new_dislike


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
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    rating = MovieRating(
        **rating_data.model_dump(exclude_unset=True),
        movie_id=movie_id,
        user_id=current_user.id
    )

    try:
        db.add(rating)
        await db.commit()
        await db.refresh(rating)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return rating


# Authorization endpoint
@router.post("/movies/my/favorites", response_model=MovieFavouriteResponseSchema, status_code=status.HTTP_200_OK)
async def add_movie_favorites(
    movie_data: MovieFavouriteSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(Movie).where(Movie.name == movie_data.movie_name)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given name was not found."
        )

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
@router.get("/movies/my/favorites")
async def get_movie_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = (
        select(MovieFavourite)
        .where(MovieFavourite.user_id == current_user.id)
        .options(joinedload(MovieFavourite.movie))
        .order_by(MovieFavourite.id.desc())
    )
    result = await db.execute(query)
    favourite_movies = result.scalars().all()

    if not favourite_movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No favourite movies found.")

    favourite_movie_list = [MovieFavouriteResponseSchema.model_validate(fav_movie) for fav_movie in favourite_movies]

    return favourite_movie_list

# Authorization endpoint
@router.delete("/movies/my/favorites/{movie_id}")
async def delete_movie_favorites(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    query = select(MovieFavourite).where(MovieFavourite.movie_id == movie_id, MovieFavourite.user_id == current_user.id)
    result = await db.execute(query)
    favourite_movie = result.scalars().first()

    await db.delete(favourite_movie)
    await db.commit()

    return {"detail": "Favourite Movie deleted successfully."}


# Moderator endpoint
@router.post("/genres", response_model=GenreDetailSchema, status_code=status.HTTP_201_CREATED)
async def create_genre(
    genre_data: GenreCreateShema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Genre).where(Genre.name == genre_data.name)
    result = await db.execute(query)
    existing_genre = result.scalars().first()
    if existing_genre:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Genre with that name already exists")

    new_genre = Genre(name=genre_data.name)

    try:
        db.add(new_genre)
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Genre with the name '{genre_data.name}' already exists"
        )

    return GenreDetailSchema.model_validate(new_genre)


# Public endpoint
@router.get("/genres", response_model=GenreListResponseSchema)
async def get_genre_list(db: AsyncSession = Depends(get_postgresql_db)) -> GenreListResponseSchema:

    query = select(Genre).order_by(Genre.id.desc())
    result = await db.execute(query)
    genres = result.scalars().all()

    if not genres:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No genres found.")

    genre_list = [GenreDetailSchema.model_validate(genre) for genre in genres]

    return GenreListResponseSchema(genres=genre_list)


# Moderator endpoint
@router.patch("/genres/{genre_id}", status_code=status.HTTP_200_OK)
async def update_genre(
    genre_id: int,
    genre_data: GenreUpdateShema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Genre).where(Genre.id == genre_id)
    result = await db.execute(query)
    genre = result.scalars().first()

    if not genre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre with the given ID was not found."
        )

    for field, value in genre_data.model_dump(exclude_unset=True).items():
        setattr(genre, field, value)

    try:
        await db.commit()
        await db.refresh(genre)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return {"detail": "Genre updated successfully."}


# Moderator endpoint
@router.delete("/genres/{genre_id}")
async def delete_genre(
    genre_id: int,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Genre).where(Genre.id == genre_id)
    result = await db.execute(query)
    genre = result.scalars().first()

    if not genre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre with the given ID was not found."
        )

    await db.delete(genre)
    await db.commit()

    return {"detail": "Genre deleted successfully."}


# Moderator endpoint
@router.post("/stars", response_model=StarResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_star(
    star_data: StarCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Star).where(Star.name == star_data.name)
    result = await db.execute(query)
    existing_star = result.scalars().first()

    if existing_star:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Star with that name already exists")

    new_star = Star(name=star_data.name)

    try:
        db.add(new_star)
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Star with the name '{new_star.name}' already exists"
        )

    return StarResponseSchema.model_validate(new_star)


# Public endpoint
@router.get("/stars", response_model=StarListResponseSchema)
async def get_star_list(db: AsyncSession = Depends(get_postgresql_db)) -> StarListResponseSchema:
    query = select(Star).order_by(Star.id.desc())
    result = await db.execute(query)
    stars = result.scalars().all()

    if not stars:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No stars found.")

    star_list = [StarResponseSchema.model_validate(star) for star in stars]

    return StarListResponseSchema(stars=star_list)


# Moderator endpoint
@router.patch("/stars/{star_id}")
async def update_star(
    star_id: int,
    star_data: StarUpdateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Star).where(Star.id == star_id)
    result = await db.execute(query)
    star = result.scalars().first()

    if not star:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Star with the given ID was not found."
        )

    for field, value in star_data.model_dump(exclude_unset=True).items():
        setattr(star, field, value)

    try:
        await db.commit()
        await db.refresh(star)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return {"detail": "Star updated successfully."}


# Moderator endpoint
@router.delete("/stars/{star_id}")
async def delete_star(
    star_id: int,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Star).where(Star.id == star_id)
    result = await db.execute(query)
    star = result.scalars().first()

    if not star:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Star with the given ID was not found."
        )

    await db.delete(star)
    await db.commit()

    return {"detail": "Star deleted successfully."}


# Moderator endpoint
@router.post("/directors", response_model=DirectorResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_director(
    director_data: DirectorCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Director).where(Director.name == director_data.name)
    result = await db.execute(query)
    existing_director = result.scalars().first()

    if existing_director:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Director with that name already exists")

    new_director = Director(name=director_data.name)

    try:
        db.add(new_director)
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Director with the name '{new_director.name}' already exists"
        )

    return DirectorResponseSchema.model_validate(new_director)


# Public endpoint
@router.get("/directors", response_model=DirectorListResponseSchema)
async def get_director_list(db: AsyncSession = Depends(get_postgresql_db)):
    query = select(Director).order_by(Director.id.desc())
    result = await db.execute(query)
    directors = result.scalars().all()

    if not directors:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No directors found.")

    director_list = [DirectorResponseSchema.model_validate(director) for director in directors]

    return DirectorListResponseSchema(directors=director_list)


# Moderator endpoint
@router.patch("/directors/{director_id}")
async def update_director(
    director_id: int,
    director_data: DirectorUpdateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Director).where(Director.id == director_id)
    result = await db.execute(query)
    director = result.scalars().first()

    if not director:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Director with the given ID was not found."
        )

    for field, value in director_data.model_dump(exclude_unset=True).items():
        setattr(director, field, value)

    try:
        await db.commit()
        await db.refresh(director)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return {"detail": "Director updated successfully."}


# Moderator endpoint
@router.delete("/directors/{director_id}")
async def delete_director(
    director_id: int,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not enough permissions")

    query = select(Director).where(Director.id == director_id)
    result = await db.execute(query)
    director = result.scalars().first()

    if not director:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Director with the given ID was not found."
        )

    await db.delete(director)
    await db.commit()

    return {"detail": "Director deleted successfully."}

