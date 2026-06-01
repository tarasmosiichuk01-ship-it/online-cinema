from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config.dependencies import get_moderator_user, get_current_user
from config.database import get_postgresql_db
from models.accounts import User
from models.movies import Genre, Movie
from schemas.movies import (
    GenreDetailSchema,
    GenreCreateSchema,
    GenreListResponseSchema,
    GenreWithMoviesCountSchema,
    GenreMoviesListResponseSchema,
    GenreUpdateSchema
)

router = APIRouter()


# Moderator endpoint
@router.post(
    "/genres",
    response_model=GenreDetailSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_genre(
    genre_data: GenreCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    query = select(Genre).where(Genre.name.ilike(genre_data.name))
    result = await db.execute(query)
    existing_genre = result.scalars().first()

    if existing_genre:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Genre with that name already exists")

    new_genre = Genre(name=genre_data.name)

    try:
        db.add(new_genre)
        await db.commit()
        await db.refresh(new_genre)

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

    query = (
        select(Genre, func.count(Movie.id).label("movies_count"))
        .join(Genre.movies, isouter=True)
        .group_by(Genre.id)
        .order_by(Genre.id.desc())
    )
    result = await db.execute(query)
    genre_rows = result.all()

    if not genre_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No genres found.")

    genre_list = [
        GenreWithMoviesCountSchema(
            id=genre.id,
            name=genre.name,
            movies_count=count,
            movies_url=f"http://127.0.0.1:8000/api/v1/genres/{genre.id}/movies",
        )
        for genre, count in genre_rows
    ]

    return GenreListResponseSchema(genres=genre_list)


# Authorization endpoint
@router.get(
    "/genres/{genre_id}/movies",
    response_model=GenreMoviesListResponseSchema,
    status_code=status.HTTP_200_OK
)
async def get_movies_by_genre(
    genre_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
) -> GenreMoviesListResponseSchema:
    query = (
        select(Genre)
        .where(Genre.id == genre_id)
        .options(selectinload(Genre.movies))
    )
    result = await db.execute(query)
    genre = result.scalars().first()

    if not genre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre with the given ID was not found."
        )

    if not genre.movies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No movies found for this genre."
        )

    movie_list = [GenreDetailSchema(id=movie.id, name=movie.name) for movie in genre.movies]
    return GenreMoviesListResponseSchema(
        id=genre.id,
        name=genre.name,
        movies=movie_list
    )


# Moderator endpoint
@router.patch("/genres/{genre_id}", status_code=status.HTTP_200_OK)
async def update_genre(
    genre_id: int,
    genre_data: GenreUpdateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    query = select(Genre).where(Genre.id == genre_id)
    result = await db.execute(query)
    genre = result.scalars().first()

    if not genre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre with the given ID was not found."
        )

    if genre_data.name:
        name_query = select(Genre).where(
            Genre.name.ilike(genre_data.name),
            Genre.id != genre_id
        )
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Genre with the name '{genre_data.name}' already exists."
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
