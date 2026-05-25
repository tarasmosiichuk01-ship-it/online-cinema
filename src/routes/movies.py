import math
from _pyrepl.commands import refresh

from fastapi import APIRouter, status, Query, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.dependencies import get_moderator_user
from database import get_postgresql_db
from models.accounts import User, UserGroupEnum
from models.movies import Movie, Genre
from schemas.movies import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema, \
    GenreListResponseSchema, GenreDetailSchema, GenreCreateShema

router = APIRouter()


@router.get(
    "/movies",
    response_model=MovieListResponseSchema
)
async def get_movie_list(
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    db: AsyncSession = Depends(get_postgresql_db),
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
        await refresh(new_genre)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Genre with the name '{genre_data.name}' already exists"
        )


@router.get("/genres", response_model=GenreListResponseSchema)
async def get_genre_list(db: AsyncSession = Depends(get_postgresql_db)) -> GenreListResponseSchema:

    query = select(Genre).order_by(Genre.id.desc())
    result = await db.execute(query)
    genres = result.scalars().all()

    if not genres:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No genres found.")

    genre_list = [GenreDetailSchema.model_validate(genre) for genre in genres]

    return GenreListResponseSchema(genres=genre_list)