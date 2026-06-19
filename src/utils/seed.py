import asyncio
from sqlalchemy import select

from config.database import AsyncPostgresqlSession
from models.accounts import UserGroupEnum, UserGroup
import models.movies  # noqa: F401
import models.orders  # noqa: F401
import models.payments  # noqa: F401
import models.shopping_carts  # noqa: F401


async def seed_user_groups():
    """
    Seeds the database with default user groups.

    Iterates over all values in UserGroupEnum and creates a UserGroup
    record for each one if it does not already exist in the database.
    This function is idempotent — running it multiple times will not
    create duplicate records.
    """
    async with AsyncPostgresqlSession() as session:
        for group in UserGroupEnum:
            result = await session.execute(select(UserGroup).where(UserGroup.name == group))
            existing_users = result.scalar_one_or_none()
            if not existing_users:
                session.add(UserGroup(name=group))
        await session.commit()


async def main():
    """
    Entry point for the seeding script.

    Calls all seeding functions to populate the database
    with required initial data.
    """
    await seed_user_groups()


if __name__ == "__main__":
    asyncio.run(main())
