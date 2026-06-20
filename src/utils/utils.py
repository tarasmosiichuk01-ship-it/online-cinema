import asyncio
from typing import Optional, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_create(db: AsyncSession, model, **kwargs):
    """
    Retrieves an existing instance of the model from the database
    or creates a new one if it does not exist.

    Args:
        db: The async database session.
        model: The SQLAlchemy model class to query or create.
        **kwargs: Field values used to filter the existing instance
                  or create a new one.

    Returns:
        The existing or newly created model instance.
    """
    result = await db.execute(select(model).filter_by(**kwargs))
    instance = result.scalar_one_or_none()
    if not instance:
        instance = model(**kwargs)
        db.add(instance)
    return instance


async def resolve_movie_relations(
    db: AsyncSession,
    genres: Optional[List[str]] = None,
    stars: Optional[List[str]] = None,
    directors: Optional[List[str]] = None,
    certification: Optional[str] = None,
) -> Tuple[Optional[List], Optional[List], Optional[List], Optional[any]]:
    """
    Creates or retrieves related entities for the movie in parallel.
    Returns a tuple of ORM objects (genres, stars, directors, certification).
    If no argument is passed (None), returns None for this element.
    """
    from models.movies import Genre, Star, Director, Certification

    genre_tasks = (
        [get_or_create(db=db, model=Genre, name=genre) for genre in genres]
        if genres is not None
        else []
    )
    star_tasks = (
        [get_or_create(db=db, model=Star, name=star) for star in stars]
        if stars is not None
        else []
    )
    director_tasks = (
        [get_or_create(db=db, model=Director, name=director) for director in directors]
        if directors is not None
        else []
    )

    resolved_genres = (
        await asyncio.gather(*genre_tasks)
        if genre_tasks
        else (None if genres is None else [])
    )
    resolved_stars = (
        await asyncio.gather(*star_tasks)
        if star_tasks
        else (None if stars is None else [])
    )
    resolved_directors = (
        await asyncio.gather(*director_tasks)
        if director_tasks
        else (None if directors is None else [])
    )

    resolved_certification = None
    if certification:
        resolved_certification = await get_or_create(
            db=db, model=Certification, name=certification
        )

    return resolved_genres, resolved_stars, resolved_directors, resolved_certification
