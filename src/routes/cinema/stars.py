from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config.dependencies import get_moderator_user
from config.database import get_postgresql_db
from models.accounts import User
from models.movies import Star
from schemas.movies import (
    StarResponseSchema,
    StarCreateSchema,
    StarListResponseSchema,
    StarUpdateSchema
)

router = APIRouter()


@router.post(
    "/stars",
    response_model=StarResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new movie star (Moderator only)",
    description=(
        "<h3>This endpoint allows moderators to register a new movie star (actor/actress) in the system. "
        "It implements a case-insensitive check (`ilike`) on the star's name to avoid duplication. "
        "If a duplicate name is caught during the application lookup or triggers a unique constraint violation "
        "at the database level due to a race condition, an appropriate error response is returned.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request if the star's name already exists based on application-level checks.",
            "content": {
                "application/json": {
                    "example": {"detail": "Star with that name already exists"}
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
            "description": "Conflict error caught by unique constraints during a database transaction race condition.",
            "content": {
                "application/json": {
                    "example": {"detail": "Star with the name '...' already exists"}
                }
            },
        }
    }
)
async def create_star(
    star_data: StarCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Register a new movie star entry in the system catalog (asynchronously).

    This function coordinates the addition of a `Star` entity. It secures execution scope through
    role-based dependency verification (`get_moderator_user`), applies case-insensitive pre-checks
    to maintain domain data uniqueness, and wraps database persistence in a block that catches
    and handles `IntegrityError` failures cleanly via a rollback operation.

    :param star_data: Request body payload containing the metadata (name) of the star to create.
    :type star_data: StarCreateSchema
    :param current_user: The authenticated user profile verifying elevated moderator roles.
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A validated schema representation of the newly created movie star database record.
    :rtype: StarResponseSchema

    :raises HTTPException: Raises a 400 error if the star name is already taken (case-insensitive application check).
    :raises HTTPException: Raises a 409 error if a unique constraint violation occurs during database commit.
    """
    query = select(Star).where(Star.name.ilike(star_data.name))
    result = await db.execute(query)
    existing_star = result.scalars().first()

    if existing_star:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Star with that name already exists"
        )

    new_star = Star(name=star_data.name)

    try:
        db.add(new_star)
        await db.commit()
        await db.refresh(new_star)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Star with the name '{new_star.name}' already exists"
        )

    return StarResponseSchema.model_validate(new_star)


@router.get(
    "/stars",
    response_model=StarListResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get all movie stars",
    description=(
        "<h3>This public endpoint retrieves a complete list of all movie stars (actors/actresses) "
        "registered in the catalog. The collection is returned in ascending order based on their unique ID. "
        "If no star records are found within the database, it returns a clear 404 error response.</h3>"
    ),
    responses={
        404: {
            "description": "Not Found if the star catalog is currently empty.",
            "content": {
                "application/json": {
                    "example": {"detail": "No stars found."}
                }
            },
        }
    }
)
async def get_star_list(db: AsyncSession = Depends(get_postgresql_db)) -> StarListResponseSchema:
    """
        Retrieve the entire collection of movie stars from the database (asynchronously).

        This function performs a straightforward relational fetch operation using SQLAlchemy.
        It streams all available `Star` records sorted sequentially by their primary key, validates
        each database row against the structural item schema, and bundles them into a list response envelope.

        :param db: The async SQLAlchemy database session (provided via dependency injection).
        :type db: AsyncSession

        :return: A validated list schema containing all registered movie star profiles.
        :rtype: StarListResponseSchema

        :raises HTTPException: Raises a 404 error if no star entries exist in the system database.
        """
    query = select(Star).order_by(Star.id.asc())
    result = await db.execute(query)
    stars = result.scalars().all()

    if not stars:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No stars found.")

    star_list = [StarResponseSchema.model_validate(star) for star in stars]

    return StarListResponseSchema(stars=star_list)


@router.patch(
    "/stars/{star_id}",
    status_code=status.HTTP_200_OK,
    summary="Partially update an existing movie star (Moderator only)",
    description=(
        "<h3>This endpoint allows moderators to partially update a movie star's metadata by their unique ID. "
        "It safely extracts explicitly provided attributes using `exclude_unset=True`. "
        "If a new name is specified, the endpoint performs a case-insensitive application check (`ilike`) "
        "excluding the current record's ID to prevent unique name collisions. "
        "All changes are persisted transactionally with full rollback handling on validation failure.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request if the new name already conflicts with another star, or if database integrity rules fail.",
            "content": {
                "application/json": {
                    "example": {"detail": "Star with the name '...' already exists."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        403: {
            "description": "Forbidden if the authenticated user lacks elevated moderator privileges.",
        },
        404: {
            "description": "Not Found if no movie star record matches the specified identifier.",
            "content": {
                "application/json": {
                    "example": {"detail": "Star with the given ID was not found."}
                }
            },
        }
    }
)
async def update_star(
    star_id: int,
    star_data: StarUpdateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Partially modify a specific movie star's profile within the system catalog (asynchronously).

    This function processes dynamic single-row changes on the `Star` model. It safeguards business rules by
    validating moderator scope permissions, confirming record existence, and performing cross-record uniqueness
    lookups on unique constraints. State changes are mapped dynamically via `setattr` loop parsing, protecting
    the active session boundary against concurrent exceptions with an explicit `IntegrityError` rollback point.

    :param star_id: The ID of the target movie star extracted from the path URL.
    :type star_id: int
    :param star_data: The Pydantic schema containing partial fields to be updated.
    :type star_data: StarUpdateSchema
    :param current_user: The authenticated user profile verifying elevated moderator roles.
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A confirmation dictionary indicating a completely successful database transaction update.
    :rtype: dict

    :raises HTTPException: Raises a 404 error if the targeted star record does not exist.
    :raises HTTPException: Raises a 400 error if name uniqueness checks fail or data mutations break schema integrity.
    """
    query = select(Star).where(Star.id == star_id)
    result = await db.execute(query)
    star = result.scalars().first()

    if not star:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Star with the given ID was not found."
        )

    if star_data.name:
        name_query = select(Star).where(
            Star.name.ilike(star_data.name),
            Star.id != star_id
        )
        name_result = await db.execute(name_query)
        if name_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Star with the name '{star_data.name}' already exists."
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
