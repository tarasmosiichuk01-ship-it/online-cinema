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


@pytest.mark.asyncio
async def test_logout_sqlalchemy_error(client):
    """
    Test logout when a database error occurs.

    Ensures that the endpoint returns a 500 status code and an appropriate
    error message when a SQLAlchemyError is raised during the commit operation.
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = MagicMock()

    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        with patch("routes.accounts.AsyncSession.delete", new_callable=AsyncMock):
            with patch("routes.accounts.AsyncSession.commit", side_effect=SQLAlchemyError):
                response = await client.post(
                    "/api/v1/accounts/logout/",
                    json={"refresh_token": "Test_token123!@#"}
                )

    assert response.status_code == 500
    assert response.json()["detail"] == "An error occurred while processing the request."


@pytest.mark.asyncio
async def test_logout_success(client):
    """
    Test successful logout.

    Ensures that the endpoint returns a 200 status code and a success message
    when a valid refresh token is provided and all database operations succeed.
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = MagicMock()
    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        with patch("routes.accounts.AsyncSession.delete", new_callable=AsyncMock):
            with patch("routes.accounts.AsyncSession.commit", new_callable=AsyncMock):
                response = await client.post(
                    "/api/v1/accounts/logout/",
                    json={"refresh_token": "Test_token123!@#"}
                )
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out."


@pytest.mark.asyncio
async def test_change_password_with_unconfirmed_password(authenticated_client):
    """
    Test change password when new passwords do not match.

    Ensures that the endpoint returns a 400 status code when
    new_password and confirm_password fields are different.
    """
    client, mock_user = authenticated_client
    payload = {
        "old_password": "Test1234!",
        "new_password": "NewTest1234!",
        "confirm_password": "ConfirmTest1234!",
    }

    response = await client.post(
        "/api/v1/accounts/change-password/",
        json=payload
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "New passwords do not match"

