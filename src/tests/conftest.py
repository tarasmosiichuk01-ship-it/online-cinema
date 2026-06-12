import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from dotenv import load_dotenv
from sqlalchemy import select

from config.dependencies import get_accounts_email_notificator, get_settings, get_current_user
from models.accounts import UserGroupEnum, UserGroup, User
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager

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


@pytest_asyncio.fixture(scope="function")
async def db_session_commit():
    async with AsyncPostgresqlSession() as session:
        yield session


@pytest_asyncio.fixture(scope="session")
async def jwt_manager() -> JWTAuthManagerInterface:
    settings = get_settings()
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )

@pytest_asyncio.fixture
async def authenticated_client(client):
    mock_user = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield client, mock_user
    app.dependency_overrides.pop(get_current_user)


@pytest_asyncio.fixture
async def moderator_client(client, db_session_commit, jwt_manager):
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.MODERATOR)
    result = await db_session_commit.execute(query)
    moderator_group = result.scalars().first()

    moderator = User.create(
        email="moderator@example.com",
        raw_password="Moderator1234!",
        group_id=moderator_group.id
    )
    moderator.is_active = True
    db_session_commit.add(moderator)
    await db_session_commit.commit()

    access_token = jwt_manager.create_access_token({"user_id": moderator.id})
    client.headers.update({"Authorization": f"Bearer {access_token}"})

    yield client

    await db_session_commit.delete(moderator)
    await db_session_commit.commit()


@pytest_asyncio.fixture
async def authorized_client(client, db_session_commit, jwt_manager):
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session_commit.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="authorized_user@example.com",
        raw_password="User1234!",
        group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.commit()

    access_token = jwt_manager.create_access_token({"user_id": user.id})
    client.headers.update({"Authorization": f"Bearer {access_token}"})

    yield client, user

    await db_session_commit.delete(user)
    await db_session_commit.commit()
