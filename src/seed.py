from sqlalchemy import select

from database import AsyncPostgresqlSession
from models.accounts import UserGroupEnum, UserGroup


async def seed_user_groups():
    async with AsyncPostgresqlSession() as session:
        for group in UserGroupEnum:
            result = await session.execute(select(UserGroup).where(UserGroup.name == group))
            existing_users = result.scalar_one_or_none()
            if not existing_users:
                session.add(UserGroup(name=group))
        await session.commit()

async def main():
    await seed_user_groups()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())