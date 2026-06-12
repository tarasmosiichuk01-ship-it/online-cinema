from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.asyncio
async def test_logout_user_unknown_token(client):
    """
    Test logout with an unknown refresh token.

    Ensures that the endpoint returns a 400 status code and an appropriate
    error message when the provided refresh token does not exist in the database.
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        response = await client.post(
            "/api/v1/accounts/logout/",
            json={"refresh_token": "nonexistent_token"}
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid refresh token."

