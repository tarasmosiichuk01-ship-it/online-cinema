from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from models.accounts import User, ActivationToken, UserGroup, UserGroupEnum


@pytest.mark.asyncio
async def test_register_user_success(client, db_session):
    """
    Test successful user registration.

    Validates that a new user and an activation token are created in the database.
    """
    payload = {
        "email": "testuser@example.com",
        "password": "Test1234!",
    }

    response = await client.post("/api/v1/accounts/register/", json=payload)
    assert response.status_code == 201

    response_data = response.json()
    assert response_data["email"] == payload["email"], "Returned email does not match."
    assert "id" in response_data, "Response does not contain user ID."

    query_user = select(User).where(User.email == payload["email"])
    result = await db_session.execute(query_user)
    created_user = result.scalars().first()
    assert created_user is not None, "User was not created in the database."
    assert created_user.email == payload["email"], "Created user's email does not match."

    query_token = select(ActivationToken).where(ActivationToken.user_id == created_user.id)
    result = await db_session.execute(query_token)
    activation_token = result.scalars().first()
    assert activation_token is not None, "Activation token was not created in the database."
    assert activation_token.user_id == created_user.id, "Activation token's user_id does not match."
    assert activation_token.token is not None, "Activation token has no token value."

    expires_at = activation_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    assert expires_at > datetime.now(timezone.utc), "Activation token is already expired."


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_password, expected_error", [
    ("short", "Password must contain at least 8 characters."),
    ("NoDigitHere!", "Password must contain at least one digit."),
    ("nodigitnorupper@", "Password must contain at least one uppercase letter."),
    ("NOLOWERCASE1@", "Password must contain at least one lower letter."),
    ("NoSpecial123", "Password must contain at least one special character: @, $, !, %, *, ?, #, &."),
])
async def test_register_user_password_validation(client, seed_user_groups, invalid_password, expected_error):
    """
    Test password strength validation in the user registration endpoint.

    Ensures that when an invalid password is provided, the endpoint returns the appropriate
    error message and a 422 status code.

    Args:
        client: The asynchronous HTTP client fixture.
        seed_user_groups: Fixture that seeds the default user groups.
        invalid_password (str): The password to test.
        expected_error (str): The expected error message substring.
    """
    payload = {
        "email": "testuser@example.com",
        "password": invalid_password,
    }

    response = await client.post("/api/v1/accounts/register/", json=payload)
    assert response.status_code == 422, "Expected status code 422 for invalid input."

    response_data = response.json()
    assert expected_error in str(response_data), f"Expected error message: {expected_error}"


@pytest.mark.asyncio
async def test_register_user_conflict(client, db_session, seed_user_groups):
    """
    Test user registration conflict.

    Ensures that trying to register a user with an existing email
    returns a 409 Conflict status and the correct error message.

    Args:
        client: The asynchronous HTTP client fixture.
        db_session: The asynchronous database session fixture.
        seed_user_groups: Fixture that seeds default user groups.
    """
    payload = {
        "email": "testuser1@example.com",
        "password": "Test1234!",
    }

    response_first = await client.post("/api/v1/accounts/register/", json=payload)
    assert response_first.status_code == 201, "Expected status code 201 for the first registration."

    query = select(User).where(User.email == payload["email"])
    result = await db_session.execute(query)
    created_user = result.scalars().first()
    assert created_user is not None, "User should be created after the first registration."

    response_second = await client.post("/api/v1/accounts/register/", json=payload)
    assert response_second.status_code == 409, "Expected status code 409 for a duplicate registration."

    response_data = response_second.json()
    expected_message = f"A user with this email {payload['email']} already exists."
    assert response_data["detail"] == expected_message, f"Expected error message: {expected_message}"


@pytest.mark.asyncio
async def test_register_user_internal_server_error(client, seed_user_groups):
    """
    Test server error during user registration.

    Ensures that a 500 Internal Server Error is returned when a database operation fails.

    This test patches the commit method of the AsyncSession to simulate a SQLAlchemyError,
    then verifies that the registration endpoint returns the appropriate HTTP 500 error
    with the expected error message.
    """
    payload = {
        "email": "erroruser@example.com",
        "password": "Test1234!",
    }

    with patch("routes.accounts.AsyncSession.commit", side_effect=SQLAlchemyError):
        response = await client.post("/api/v1/accounts/register/", json=payload)

        assert response.status_code == 500, "Expected status code 500 for internal server error."

        response_data = response.json()
        expected_message = "An error occurred during user creation."
        assert response_data["detail"] == expected_message, f"Expected error message: {expected_message}"


@pytest.mark.asyncio
async def test_activate_account_success(client, db_session, seed_user_groups):
    """
    Test successful activation of a user account.

    Steps:
    - Register a new user.
    - Verify the user is inactive.
    - Activate the user using the activation token.
    - Verify the user is activated and the token is deleted.
    """
    registration_payload = {
        "email": "activate_testuser@example.com",
        "password": "Test1234!"
    }

    registration_response = await client.post("/api/v1/accounts/register/", json=registration_payload)
    assert registration_response.status_code == 201, "Expected status code 201 for successful registration."

    query_user = (
        select(User)
        .options(joinedload(User.activation_token))
        .where(User.email == registration_payload["email"])
    )
    result_user = await db_session.execute(query_user)
    user = result_user.scalars().first()
    assert user is not None, "User was not created in the database."
    assert not user.is_active, "Newly registered user should not be active."

    assert user.activation_token is not None and user.activation_token.token is not None, \
        "Activation token was not created in the database."

    activation_response = await client.get(f"/api/v1/accounts/activate/{user.activation_token.token}/")
    assert activation_response.status_code == 200, "Expected status code 200 for successful activation."
    assert activation_response.json()["message"] == "User account activated successfully."

    await db_session.refresh(user)
    assert user.is_active, "User should be active after successful activation."

    query_token = select(ActivationToken).where(ActivationToken.user_id == user.id)
    result_token = await db_session.execute(query_token)
    token = result_token.scalars().first()
    assert token is None, "Activation token should be deleted after successful activation."


@pytest.mark.asyncio
async def test_activate_user_with_expired_token(client, db_session, seed_user_groups):
    """
    Test activation with an expired token.

    Ensures that the endpoint returns a 400 error when the activation token is expired.
    Steps:
    - Create a new inactive user directly in the database.
    - Create an activation token with an expiration date in the past.
    - Attempt to activate the account with the expired token.
    - Verify that the response is a 400 error with the expected error message.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="expired_testuser@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    db_session.add(user)
    await db_session.flush()

    token = ActivationToken(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=2)
    )
    db_session.add(token)
    await db_session.flush()
    token_value = token.token
    await db_session.commit()

    activation_response = await client.get(f"/api/v1/accounts/activate/{token_value}/")

    assert activation_response.status_code == 400
    assert activation_response.json()["detail"] == "Invalid or expired activation token."


@pytest.mark.asyncio
async def test_activate_user_with_deleted_token(client, db_session, seed_user_groups):
    """
    Test activation with a deleted token.

    Ensures that the endpoint returns a 400 error when the activation token has been deleted.

    Steps:
    - Create a new inactive user directly in the database.
    - Create an activation token for the user.
    - Delete the activation token from the database.
    - Attempt to activate the account using the deleted token.
    - Verify that a 400 error is returned with the appropriate error message.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="deleted_token_testuser@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    db_session.add(user)
    await db_session.flush()

    token = ActivationToken(user_id=user.id)
    db_session.add(token)
    await db_session.flush()
    token_value = token.token

    await db_session.delete(token)
    await db_session.commit()

    activation_response = await client.get(f"/api/v1/accounts/activate/{token_value}/")

    assert activation_response.status_code == 400
    assert activation_response.json()["detail"] == "Invalid or expired activation token."
