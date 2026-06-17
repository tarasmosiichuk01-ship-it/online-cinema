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


@router.post(
    "/genres",
    response_model=GenreDetailSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new genre (Moderator only)",
    description=(
        "<h3>This endpoint allows moderators to add a new movie genre to the catalog. "
        "It enforces strict data uniqueness by performing a case-insensitive check (`ilike`) on the genre name. "
        "If the genre already exists in the system or if a concurrent transaction triggers a database "
        "unique constraint violation, it throws an appropriate error to maintain data integrity.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request if the genre name is already taken based on application-level checks.",
            "content": {
                "application/json": {
                    "example": {"detail": "Genre with that name already exists"}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        403: {
            "description": "Forbidden if the authenticated user lacks elevated moderator privileges.",
        },
        409: {
            "description": "Conflict error raised by database unique constraints during a race condition.",
            "content": {
                "application/json": {
                    "example": {"detail": "Genre with the name '...' already exists"}
                }
            },
        }
    }
)
async def create_genre(
    genre_data: GenreCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Register a new movie genre inside the catalog system (asynchronously).

    This function handles the creation of a `Genre` entity. It secures the process via role-based
    dependency injection (`get_moderator_user`), applies defensive database lookups to prevent duplication,
    and wraps the state persistence within a transaction block that handles unexpected `IntegrityError` failures.

    :param genre_data: Request body payload containing the name of the genre to create.
    :type genre_data: GenreCreateSchema
    :param current_user: The authenticated user profile verifying elevated moderator roles.
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A parsed and validated database model representing the newly recorded genre.
    :rtype: GenreDetailSchema

    :raises HTTPException: Raises a 400 error if a genre with the same name exists (case-insensitive).
    :raises HTTPException: Raises a 409 error if a unique constraint is violated at the database level.
    """
    query = select(Genre).where(Genre.name.ilike(genre_data.name))
    result = await db.execute(query)
    existing_genre = result.scalars().first()

    if existing_genre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Genre with that name already exists"
        )

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


@router.get(
    "/genres",
    response_model=GenreListResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get all genres with movie counts",
    description=(
        "<h3>This public endpoint retrieves a list of all movie genres available in the catalog. "
        "It performs an aggregation using an outer join to dynamically calculate the total number of "
        "movies linked to each genre. Additionally, it generates a hypermedia direct URL (`movies_url`) "
        "for fetching movies specific to that genre. "
        "The results are ordered chronologically by the genre ID in descending order.</h3>"
    ),
    responses={
        404: {
            "description": "Not Found if no genre records exist in the database.",
            "content": {
                "application/json": {
                    "example": {"detail": "No genres found."}
                }
            },
        }
    }
)
async def get_genre_list(db: AsyncSession = Depends(get_postgresql_db)) -> GenreListResponseSchema:
    """
    Retrieve all catalog genres compiled with their aggregated movie counts (asynchronously).

    This function executes an optimized relational query using an SQL LEFT OUTER JOIN and a `GROUP BY` clause
    via SQLAlchemy. This allows it to fetch both the genre metadata and the calculated `movies_count`
    in a single database round-trip, preventing N+1 anomalies. The resulting dataset is parsed and mapped
    into extended schemas that inject resource hypermedia links.

    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A structured list schema containing validated genre profiles with counters and hypermedia references.
    :rtype: GenreListResponseSchema

    :raises HTTPException: Raises a 404 error if the genre catalog is completely empty.
    """
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


@router.get(
    "/genres/{genre_id}/movies",
    response_model=GenreMoviesListResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get movies by specific genre",
    description=(
            "<h3>This endpoint retrieves a list of all movies associated with a specific genre identifier. "
            "It requires user authentication and checks the database for the existence of the target genre. "
            "If the genre exists but has no linked movies, or if the genre ID itself is invalid, "
            "it returns a targeted 404 error response to guide the client.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the genre does not exist or if no movies are mapped to this genre.",
            "content": {
                "application/json": {
                    "example": {"detail": "No movies found for this genre."}
                }
            },
        }
    }
)
async def get_movies_by_genre(
    genre_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
) -> GenreMoviesListResponseSchema:
    """
    Retrieve all movies mapped to a specified genre from the catalog (asynchronously).

    This function fetches a single `Genre` record filtering by its primary key. It avoids
    the N+1 loading issue by eagerly preloading the related `movies` collection using the
    `selectinload` strategy. It enforces business logic constraints by ensuring both the
    genre domain entity and its nested relationships contain active entries before serialization.

    :param genre_id: The ID of the target genre extracted from the path URL.
    :type genre_id: int
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A structured schema containing the genre details and its nested collection of validated movies.
    :rtype: GenreMoviesListResponseSchema

    :raises HTTPException: Raises a 404 error if the genre record is missing.
    :raises HTTPException: Raises a 404 error if the genre is valid but contains no assigned movies.
    """
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
