from typing import AsyncGenerator
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import AsyncPostgresqlSession


async def override_get_postgresql_db() -> AsyncGenerator[AsyncSession, None]:

    async with AsyncPostgresqlSession() as session:
        yield session


async def override_get_email_notificator():
    mock = AsyncMock()
    mock.send_activation_email = AsyncMock()
    return mock
