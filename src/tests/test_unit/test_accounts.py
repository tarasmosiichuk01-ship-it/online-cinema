from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models.accounts import User


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


@pytest.mark.asyncio
async def test_change_password_verify_password(authenticated_client):
    """
    Test change password when old password is incorrect.

    Ensures that the endpoint returns a 400 status code when
    the provided old password does not match the current password.
    """
    client, mock_user = authenticated_client
    mock_user.verify_password.return_value = False

    payload = {
        "old_password": "Test1234!",
        "new_password": "NewTest1234!",
        "confirm_password": "NewTest1234!",
    }

    response = await client.post(
        "/api/v1/accounts/change-password/",
        json=payload
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect current password"


@pytest.mark.asyncio
async def test_change_password_same_as_old(authenticated_client):
    """
    Test change password when new password is the same as old password.

    Ensures that the endpoint returns a 400 status code when
    the new password matches the current password.
    """
    client, mock_user = authenticated_client
    mock_user.verify_password.return_value = True

    payload = {
        "old_password": "Test1234!",
        "new_password": "Test1234!",
        "confirm_password": "Test1234!",
    }

    response = await client.post(
        "/api/v1/accounts/change-password/",
        json=payload
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "New password must be different from old password"


@pytest.mark.asyncio
async def test_change_password_sqlalchemy_error(authenticated_client):
    """
    Test change password when a database error occurs.

    Ensures that the endpoint returns a 500 status code and an appropriate
    error message when a SQLAlchemyError is raised during the commit operation.
    """
    client, mock_user = authenticated_client
    mock_user.verify_password.return_value = True

    payload = {
        "old_password": "Test1234!",
        "new_password": "NewTest1234!",
        "confirm_password": "NewTest1234!",
    }

    with patch("routes.accounts.AsyncSession.delete", new_callable=AsyncMock):
        with patch("routes.accounts.AsyncSession.commit", side_effect=SQLAlchemyError):
            response = await client.post(
                "/api/v1/accounts/change-password/",
                json=payload
            )

    assert response.status_code == 500
    assert response.json()["detail"] == "An error occurred while changing password."


@pytest.mark.asyncio
async def test_change_password_success(authenticated_client):
    """
    Test successful password change.

    Ensures that the endpoint returns a 200 status code and a success message
    when valid passwords are provided and all database operations succeed.
    """
    client, mock_user = authenticated_client
    mock_user.verify_password.return_value = True

    payload = {
        "old_password": "Test1234!",
        "new_password": "NewTest1234!",
        "confirm_password": "NewTest1234!",
    }

    with patch("routes.accounts.AsyncSession.delete", new_callable=AsyncMock):
        with patch("routes.accounts.AsyncSession.commit", new_callable=AsyncMock):
            response = await client.post(
                "/api/v1/accounts/change-password/",
                json=payload
            )

    assert response.status_code == 200
    assert response.json()["message"] == "Successfully changed password."



@pytest.mark.asyncio
async def test_reset_activation_token_user_not_found(client):
    """
    Test reset activation token when user does not exist.

    Ensures that the endpoint returns a 200 status code with a generic
    message when the provided email does not exist in the database.
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None

    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        response = await client.post(
            "/api/v1/accounts/reset-activation/",
            json={"email": "user_not_found_testuser@example.com"}
        )

    assert response.status_code == 200
    assert response.json()["message"] == "If you are registered, you will receive an email with instructions."


@pytest.mark.asyncio
async def test_reset_activation_token_user_not_active(client):
    """
    Test reset activation token when user is already active.

    Ensures that the endpoint returns a 200 status code with a generic
    message when the user account is already activated.
    """
    mock_user = MagicMock()
    mock_user.is_active = True

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user

    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        response = await client.post(
            "/api/v1/accounts/reset-activation/",
            json={"email": "user_not_active@example.com"}
        )

    assert response.status_code == 200
    assert response.json()["message"] == "If you are registered, you will receive an email with instructions."


@pytest.mark.asyncio
async def test_reset_activation_token_sqlalchemy_error(client):
    """
    Test reset activation token when a database error occurs.

    Ensures that the endpoint returns a 500 status code and an appropriate
    error message when a SQLAlchemyError is raised during the commit operation.
    """
    mock_user = MagicMock()
    mock_user.is_active = False

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user

    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        with patch("routes.accounts.AsyncSession.commit", side_effect=SQLAlchemyError):
            response = await client.post(
                "/api/v1/accounts/reset-activation/",
                json={"email": "sqlalchemy_error_testuser@example.com"}
            )

    assert response.status_code == 500
    assert response.json()["detail"] == "An error occurred. Please try again later."


@pytest.mark.asyncio
async def test_reset_activation_token_success(client):
    """
    Test successful reset activation token.

    Ensures that the endpoint returns a 200 status code and a success message
    when the user exists, is not active, and all database operations succeed.
    """
    mock_user = MagicMock()
    mock_user.is_active = False

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user

    with patch("routes.accounts.AsyncSession.execute", return_value=mock_result):
        with patch("routes.accounts.AsyncSession.delete", new_callable=AsyncMock):
            with patch("routes.accounts.AsyncSession.commit", new_callable=AsyncMock):
                with patch("routes.accounts.AsyncSession.refresh", new_callable=AsyncMock):
                    response = await client.post(
                        "/api/v1/accounts/reset-activation/",
                        json={"email": "reset_activation_testuser@example.com"}
                    )

    assert response.status_code == 200
    assert response.json()["message"] == "If you are registered and not yet activated, you will receive an email."
