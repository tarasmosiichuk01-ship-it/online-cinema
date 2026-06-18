from typing import AsyncGenerator
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import AsyncPostgresqlSession


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
