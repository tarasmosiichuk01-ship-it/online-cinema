import math

from fastapi import APIRouter, status, Query, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.dependencies import get_moderator_user
from database import get_postgresql_db
from models.accounts import User, UserGroupEnum
from models.movies import Movie, Genre, Certification, Star, Director
from schemas.movies import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema, \
    GenreListResponseSchema, GenreDetailSchema, GenreCreateShema, MovieCreateSchema, MovieUpdateSchema
from utils.utils import get_or_create

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
    if not current_user.has_group(UserGroupEnum.MODERATOR):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    existing_query = select(Movie).where(
        (Movie.name == movie_data.name),
        (Movie.year == movie_data.year),
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
            certification=await get_or_create(db=db, model=Certification, name=movie_data.certification),
            genres=[await get_or_create(db=db, model=Genre, name=genre) for genre in movie_data.genres],
            stars=[await get_or_create(db=db, model=Star, name=star) for star in movie_data.stars],
            directors=[await get_or_create(db=db, model=Director, name=director) for director in movie_data.directors]
        )

        db.add(new_movie)
        await db.commit()
        await db.refresh(new_movie, ["genres", "stars", "directors"])

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
            joinedload(Movie.genres),
            joinedload(Movie.stars),
            joinedload(Movie.directors),
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

    for field, value in movie_data.model_dump(exclude_unset=True).items():
        setattr(movie, field, value)

    try:
        await db.commit()
        await db.refresh(movie)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")

    return {"detail": "Movie updated successfully."}



# Moderators endpoint
@router.delete("/movies/{movie_id}")
async def delete_movie():
    pass


# Authorization endpoint
@router.post("/movies/{movie_id}/comments")
async def create_movie_comments():
    pass


# Authorization endpoint
@router.get("/movies/{movie_id}/comments")
async def get_movie_comments():
    pass



# Authorization endpoint
@router.post("/movies/{movie_id}/like")
async def like_movie():
    pass


# Authorization endpoint
@router.post("/movies/{movie_id}/dislike")
async def dislike_movie():
    pass


# Authorization endpoint
@router.post("/movies/{movie_id}/rate")
async def rate_movie():
    pass


# Authorization endpoint
@router.post("/movies/favorites")
async def add_movie_favorites():
    pass


# Authorization endpoint
@router.get("/movies/favorites")
async def get_movie_favorites():
    pass


# Authorization endpoint
@router.delete("/movies/favorites/{movie_id}")
async def delete_movie_favorites():
    pass


# Authorization endpoint
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
        #await refresh(new_genre)

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