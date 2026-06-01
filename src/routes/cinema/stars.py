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


# Moderator endpoint
@router.post(
    "/stars",
    response_model=StarResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_star(
    star_data: StarCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

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


# Public endpoint
@router.get("/stars", response_model=StarListResponseSchema)
async def get_star_list(db: AsyncSession = Depends(get_postgresql_db)) -> StarListResponseSchema:
    query = select(Star).order_by(Star.id.asc())
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
