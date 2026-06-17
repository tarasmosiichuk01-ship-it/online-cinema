from unittest.mock import patch
import pytest
from sqlalchemy import select
from models.accounts import UserGroupEnum, UserGroup
from seed import seed_user_groups


@pytest.mark.asyncio
async def test_seed_user_groups_initial_creation(db_session):
    """
    Test for the first run on a raw database.
    Checks that all groups from the enam have been created.
    """
    with patch("seed.AsyncPostgresqlSession") as mock_session_factory:
        mock_session_factory.return_value.__aenter__.return_value = db_session

        await seed_user_groups()

    result = await db_session.execute(select(UserGroup))
    inserted_groups = result.scalars().all()

    assert len(inserted_groups) == len(UserGroupEnum)

    inserted_names = {g.name for g in inserted_groups}
    expected_names = {group for group in UserGroupEnum}
    assert inserted_names == expected_names



