from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config.dependencies import get_moderator_user
from config.database import get_postgresql_db
from models.accounts import User
from models.movies import Director
from schemas.movies import (
    DirectorResponseSchema,
    DirectorCreateSchema,
    DirectorListResponseSchema,
    DirectorUpdateSchema
)

router = APIRouter()


@router.post(
    "/directors",
    response_model=DirectorResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new director (Moderator only)",
    description=(
        "<h3>This endpoint allows moderators to add a new movie director to the system. "
        "It enforces data uniqueness by performing a case-insensitive check (`ilike`) on the director's name. "
        "If a director with the same name already exists, or if a race condition triggers an database "
        "integrity violation, an appropriate error response is returned to prevent duplicate data entries.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request if a director with the given name is already registered via application pre-checks.",
            "content": {
                "application/json": {
                    "example": {"detail": "Director with that name already exists"}
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
            "description": "Conflict error raised by a native database unique constraint failure during transactional commitment.",
            "content": {
                "application/json": {
                    "example": {"detail": "Director with the name '...' already exists"}
                }
            },
        }
    }
)
async def create_director(
    director_data: DirectorCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Register a new director record inside the catalog system (asynchronously).

    This function coordinates back-office directory additions. It verifies role permissions through the
    `get_moderator_user` dependency, applies structural defensive checks via database selection, safely handles
    concurrent transaction collisions by catching `IntegrityError` exceptions, and exposes a clean metadata profile.

    :param director_data: Request body payload carrying the desired director specifications.
    :type director_data: DirectorCreateSchema
    :param current_user: The authenticated user profile verifying elevated moderator roles.
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A parsed and validated database model representing the newly recorded director asset.
    :rtype: DirectorResponseSchema

    :raises HTTPException: Raises a 400 error if application filters catch a case-insensitive name match.
    :raises HTTPException: Raises a 409 error if concurrent backend processes trigger an IntegrityError constraint.
    """
    query = select(Director).where(Director.name.ilike(director_data.name))
    result = await db.execute(query)
    existing_director = result.scalars().first()

    if existing_director:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Director with that name already exists"
        )

    new_director = Director(name=director_data.name)

    try:
        db.add(new_director)
        await db.commit()
        await db.refresh(new_director)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Director with the name '{new_director.name}' already exists"
        )

    return DirectorResponseSchema.model_validate(new_director)


# Public endpoint
@router.get(
    "/directors",
    response_model=DirectorListResponseSchema,
    summary="Get all directors",
    description=(
        "<h3>This public endpoint retrieves a complete list of all movie directors registered in the catalog. "
        "The entries are sorted sequentially by their unique database identifier in ascending order. "
        "If the director directory is completely empty, a 404 error is raised to inform the client.</h3>"
    ),
    responses={
        404: {
            "description": "Not Found if no director records exist in the database.",
            "content": {
                "application/json": {
                    "example": {"detail": "No directors found."}
                }
            },
        }
    }
)
async def get_director_list(db: AsyncSession = Depends(get_postgresql_db)):
    """
    Retrieve the entire collection of movie directors from the catalog (asynchronously).

    This function executes a simple index query on the `Director` model, sorting the results chronologically
    by their ID. It validates the presence of records in the database, maps the SQLAlchemy objects into
    individual validation schemas, and bundles them inside a unified list response payload.

    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A encapsulated list response object containing all validated director profiles.
    :rtype: DirectorListResponseSchema

    :raises HTTPException: Raises a 404 error if the database table contains no records.
    """
    query = select(Director).order_by(Director.id.asc())
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

    query = select(Director).where(Director.id == director_id)
    result = await db.execute(query)
    director = result.scalars().first()

    if not director:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Director with the given ID was not found."
        )

    if director_data.name:
        name_query = select(Director).where(
            Director.name.ilike(director_data.name),
            Director.id != director_id
        )
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Director with the name '{director_data.name}' already exists."
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
