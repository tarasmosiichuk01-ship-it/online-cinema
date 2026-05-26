from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def get_or_create(db: AsyncSession, model, **kwargs):
    result = await db.execute(select(model).filter_by(**kwargs))
    instance = result.scalar_one_or_none()
    if not instance:
        instance = model(**kwargs)
        db.add(instance)
    return instance