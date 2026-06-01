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


# Moderator endpoint
@router.post(
    "/directors",
    response_model=DirectorResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_director(
    director_data: DirectorCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

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
@router.get("/directors", response_model=DirectorListResponseSchema)
async def get_director_list(db: AsyncSession = Depends(get_postgresql_db)):
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
