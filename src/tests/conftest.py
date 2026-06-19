import os
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock, AsyncMock

from dotenv import load_dotenv
from sqlalchemy import select

from config.dependencies import get_accounts_email_notificator, get_settings, get_current_user
from models.accounts import UserGroupEnum, UserGroup, User
from models.movies import Movie, Certification
from notifications.emails import EmailSender
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager

base_dir = Path(__file__).resolve().parent.parent.parent
env_test_path = base_dir / ".env.test"
load_dotenv(env_test_path, override=True)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config.database import get_postgresql_db
from models.base import Base
from src.main import app

settings = get_settings()

TEST_POSTGRESQL_DATABASE_URL = settings.postgres_database_url

test_postgresql_engine = create_async_engine(TEST_POSTGRESQL_DATABASE_URL, echo=False)

AsyncPostgresqlSession = async_sessionmaker(
    test_postgresql_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def override_get_postgresql_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Override for the get_postgresql_db dependency.

    Provides a test database session using the test PostgreSQL engine
    instead of the production database session.
    """
    async with AsyncPostgresqlSession() as session:
        yield session


async def override_get_email_notificator():
    """
    Override for the get_accounts_email_notificator dependency.

    Returns a mocked email notificator with all email sending methods
    replaced by AsyncMock to prevent real emails from being sent during tests.
    """
    mock = AsyncMock()
    mock.send_activation_email = AsyncMock()
    return mock


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """
    Session-scoped fixture that creates all database tables before tests
    and drops them after all tests are completed.
    """
    async with test_postgresql_engine.begin() as connect:
        await connect.run_sync(Base.metadata.create_all)

    yield

    async with test_postgresql_engine.begin() as connect:
        await connect.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="session")
async def seed_user_groups(setup_database):
    """
    Session-scoped fixture that seeds default user groups into the database.
    Depends on setup_database to ensure tables exist before seeding.
    """
    async with AsyncPostgresqlSession() as session:
        for group in UserGroupEnum:
            result = await session.execute(select(UserGroup).where(UserGroup.name == group))
            existing_users = result.scalar_one_or_none()
            if not existing_users:
                session.add(UserGroup(name=group))
        await session.commit()


@pytest_asyncio.fixture(scope="function")
async def db_session(setup_database):
    """
    Function-scoped fixture that provides a database session with automatic
    rollback after each test to ensure test isolation.
    """
    async with test_postgresql_engine.connect() as connect:
        await connect.begin()

        async with AsyncSession(connect) as session:
            yield session

        await connect.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(seed_user_groups):
    """
    Function-scoped fixture that provides an async HTTP client with
    overridden database and email notificator dependencies.
    Clears all dependency overrides after each test.
    """
    app.dependency_overrides[get_postgresql_db] = override_get_postgresql_db
    app.dependency_overrides[get_accounts_email_notificator] = override_get_email_notificator

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        yield async_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def db_session_commit():
    """
    Function-scoped fixture that provides a database session that commits
    changes. Used when tests need data to persist across multiple operations.
    """
    async with AsyncPostgresqlSession() as session:
        yield session


@pytest_asyncio.fixture(scope="session")
async def jwt_manager() -> JWTAuthManagerInterface:
    """
    Session-scoped fixture that provides a JWT manager instance
    configured with test settings for token creation and validation.
    """
    settings = get_settings()
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )


@pytest_asyncio.fixture
async def authenticated_client(client):
    """
    Function-scoped fixture that provides a client with a mocked
    current user dependency override for unit tests.
    Yields a tuple of (client, mock_user).
    """
    mock_user = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield client, mock_user
    app.dependency_overrides.pop(get_current_user)


@pytest_asyncio.fixture
async def moderator_client(client, db_session_commit, jwt_manager):
    """
    Function-scoped fixture that provides an async HTTP client
    authorized as a moderator user with a valid JWT token.
    Creates a moderator user before the test and deletes it after.
    """
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
async def admin_client(client, db_session_commit, jwt_manager):
    """
    Function-scoped fixture that provides an async HTTP client
    authorized as an admin user with a valid JWT token.
    Creates an admin user before the test and deletes it after.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.ADMIN)
    result = await db_session_commit.execute(query)
    admin_group = result.scalars().first()

    admin = User.create(
        email="admin@example.com",
        raw_password="Admin1234!",
        group_id=admin_group.id
    )
    admin.is_active = True
    db_session_commit.add(admin)
    await db_session_commit.commit()

    access_token = jwt_manager.create_access_token({"user_id": admin.id})
    client.headers.update({"Authorization": f"Bearer {access_token}"})

    yield client

    await db_session_commit.delete(admin)
    await db_session_commit.commit()


@pytest_asyncio.fixture
async def authorized_client(client, db_session_commit, jwt_manager):
    """
    Function-scoped fixture that provides an async HTTP client
    authorized as a regular user with a valid JWT token.
    Creates a user before the test and deletes it after.
    Yields a tuple of (client, user).
    """
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


@pytest_asyncio.fixture
async def test_movie(db_session_commit):
    """
    Function-scoped fixture that creates a test movie with certification
    in the database before the test and deletes it after.
    Yields the created Movie instance.
    """
    certification = Certification(name="PG-13")
    db_session_commit.add(certification)
    await db_session_commit.flush()

    movie = Movie(
        name="Test Movie",
        year=2021,
        time=120,
        imdb=7.5,
        votes=1000,
        description="Test description",
        price=9.99,
        certification_id=certification.id,
    )
    db_session_commit.add(movie)
    await db_session_commit.commit()
    await db_session_commit.refresh(movie)

    yield movie

    await db_session_commit.delete(movie)
    await db_session_commit.delete(certification)
    await db_session_commit.commit()


@pytest_asyncio.fixture
def email_sender():
    """
    Function-scoped fixture that provides an EmailSender instance
    configured with test SMTP settings and template names
    for unit testing email sending functionality.
    """
    return EmailSender(
        hostname="smtp.test.com",
        port=587,
        email="test@test.com",
        password="password",
        use_tls=True,
        template_dir="/templates",
        activation_email_template_name="activation.html",
        activation_complete_email_template_name="activation_complete.html",
        password_email_template_name="password_reset.html",
        reply_comment_template_name="reply_comment.html",
        reaction_comment_template_name="reaction_comment.html",
        confirmation_payment_template_name="confirmation_payment.html"
    )
