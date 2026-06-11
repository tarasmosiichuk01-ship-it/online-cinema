import os
from pathlib import Path
from unittest.mock import AsyncMock

from dotenv import load_dotenv
from sqlalchemy import select

from config.dependencies import get_accounts_email_notificator
from models.accounts import UserGroupEnum, UserGroup

base_dir = Path(__file__).resolve().parent.parent.parent
env_test_path = base_dir / ".env.test"
load_dotenv(env_test_path, override=True)

from typing import AsyncGenerator
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.database import get_postgresql_db
from src.models.base import Base
from src.main import app


TEST_POSTGRESQL_DATABASE_URL = os.getenv("DATABASE_URL")

test_postgresql_engine = create_async_engine(TEST_POSTGRESQL_DATABASE_URL, echo=False)

AsyncPostgresqlSession = async_sessionmaker(
    test_postgresql_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    async with test_postgresql_engine.begin() as connect:
        await connect.run_sync(Base.metadata.create_all)

    yield

    async with test_postgresql_engine.begin() as connect:
        await connect.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="session")
async def seed_user_groups(setup_database):
    async with AsyncPostgresqlSession() as session:
        for group in UserGroupEnum:
            result = await session.execute(select(UserGroup).where(UserGroup.name == group))
            existing_users = result.scalar_one_or_none()
            if not existing_users:
                session.add(UserGroup(name=group))
        await session.commit()


@pytest_asyncio.fixture(scope="function")
async def db_session(setup_database):
    async with test_postgresql_engine.connect() as connect:
        await connect.begin()

        async with AsyncSession(connect) as session:
            yield session

        await connect.rollback()


#----

async def override_get_postgresql_db() -> AsyncGenerator[AsyncSession, None]:

    async with AsyncPostgresqlSession() as session:
        yield session


async def override_get_email_notificator():
    mock = AsyncMock()
    mock.send_activation_email = AsyncMock()
    return mock


@pytest_asyncio.fixture(scope="function")
async def client(seed_user_groups):
    app.dependency_overrides[get_postgresql_db] = override_get_postgresql_db
    app.dependency_overrides[get_accounts_email_notificator] = override_get_email_notificator


    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        yield async_client

    app.dependency_overrides.clear()
