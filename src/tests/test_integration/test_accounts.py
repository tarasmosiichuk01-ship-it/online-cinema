from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select, delete, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from models.accounts import User, ActivationToken, UserGroup, UserGroupEnum, PasswordResetToken


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


@pytest.mark.asyncio
async def test_activate_already_active_user(client, db_session_commit, seed_user_groups):
    """
    Test activation of an already active user.

    Ensures that the endpoint returns a 400 error if the user is already active.
    Steps:
    - Create a new active user directly in the database.
    - Create an activation token for the user.
    - Attempt to activate the user using the activation token.
    - Verify that a 400 error with the expected error message is returned.
    """
    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db_session_commit.execute(query)
    user_group = result.scalars().first()

    user = User.create(
        email="already_active_testuser@example.com",
        raw_password="Test1234!",
        group_id=user_group.id
    )
    user.is_active = True
    db_session_commit.add(user)
    await db_session_commit.flush()

    token = ActivationToken(user_id=user.id)
    db_session_commit.add(token)
    await db_session_commit.flush()
    token_value = token.token
    await db_session_commit.commit()

    activation_response = await client.get(
        f"/api/v1/accounts/activate/{token_value}/"
    )
    assert activation_response.status_code == 400
    assert activation_response.json()["detail"] == "User account is already active."


@pytest.mark.asyncio
async def test_request_password_reset_token_success(client, db_session_commit, seed_user_groups):
    """
    Test successful password reset token request.

    Ensures that a password reset token is created for an active user.

    Steps:
    - Register a new user.
    - Mark the user as active.
    - Request a password reset token.
    - Verify that the endpoint returns status 200 and the expected success message.
    - Query the database to confirm that a PasswordResetTokenModel record was created.
    - Verify that the token's expiration date is in the future.
    """
    registration_payload = {
        "email": "reset_token_testuser@example.com",
        "password": "Test1234!"
    }
    registration_response = await client.post("/api/v1/accounts/register/", json=registration_payload)
    assert registration_response.status_code == 201, "Expected status code 201 for successful registration."

    query_user = select(User).where(User.email == registration_payload["email"])
    result_user = await db_session_commit.execute(query_user)
    user = result_user.scalars().first()
    assert user is not None, "User should exist in the database."

    user.is_active = True
    await db_session_commit.commit()

    reset_payload = {"email": registration_payload["email"]}
    reset_response = await client.post("/api/v1/accounts/forgot-password/", json=reset_payload)
    assert reset_response.status_code == 200, "Expected status code 200 for successful token request."
    assert reset_response.json()["message"] == "If you wish to reset your password, you will receive an email.", \
        "Expected success message for password reset token request."

    query_token = select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    result_token = await db_session_commit.execute(query_token)
    reset_token = result_token.scalars().first()
    assert reset_token is not None, "Password reset token should be created for the user."

    expires_at = reset_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    assert expires_at > datetime.now(timezone.utc), "Password reset token should have a future expiration date."


@pytest.mark.asyncio
async def test_request_password_reset_token_nonexistent_user(client, db_session):
    """
    Test password reset token request for a non-existent user.

    Ensures that the endpoint responds with a generic success message and that no password reset token is created
    when the email does not exist in the database.
    """
    reset_payload = {"email": "nonexistent@example.com"}

    reset_response = await client.post("/api/v1/accounts/forgot-password/", json=reset_payload)
    assert reset_response.status_code == 200, "Expected status code 200 for non-existent user request."
    assert reset_response.json()["message"] == "If you wish to reset your password, you will receive an email.", (
        "Expected generic success message for non-existent user request."
    )

    query = select(func.count(PasswordResetToken.id)).join(User).where(
        User.email == reset_payload["email"]
    )
    result = await db_session.execute(query)
    reset_token_count = result.scalar_one()
    assert reset_token_count == 0, "No password reset token should be created for non-existent user."


@pytest.mark.asyncio
async def test_request_password_reset_token_for_inactive_user(client, db_session, seed_user_groups):
    """
    Test password reset token request for a registered but inactive user.

    Ensures that the endpoint returns the generic success message and that no password reset token
    is created when the user is registered but inactive.
    """
    registration_payload = {
        "email": "inactiveuser@example.com",
        "password": "Test1234!"
    }
    registration_response = await client.post("/api/v1/accounts/register/", json=registration_payload)
    assert registration_response.status_code == 201, "Expected status code 201 for successful registration."

    query_user = select(User).where(User.email == registration_payload["email"])
    result_user = await db_session.execute(query_user)
    created_user = result_user.scalars().first()
    assert created_user is not None, "User should be created in the database."
    assert not created_user.is_active, "User should not be active after registration."

    reset_payload = {"email": registration_payload["email"]}
    reset_response = await client.post("/api/v1/accounts/forgot-password/", json=reset_payload)
    assert reset_response.status_code == 200, "Expected status code 200 for inactive user password reset request."
    assert reset_response.json()["message"] == "If you wish to reset your password, you will receive an email.", (
        "Expected generic success message for inactive user password reset request."
    )

    query_tokens = select(func.count(PasswordResetToken.id)).join(User).where(
        User.email == reset_payload["email"]
    )
    result_tokens = await db_session.execute(query_tokens)
    reset_token_count = result_tokens.scalar_one()
    assert reset_token_count == 0, "No password reset token should be created for an inactive user."


@pytest.mark.asyncio
async def test_reset_password_success(client, db_session_commit, seed_user_groups):
    """
    Test the complete password reset flow.

    Steps:
    - Register a user.
    - Activate the user.
    - Request a password reset token.
    - Use the token to reset the password.
    - Verify the password is updated in the database.
    """
    registration_payload = {
        "email": "reset_password_testuser@example.com",
        "password": "Test1234!"
    }
    registration_response = await client.post("/api/v1/accounts/register/", json=registration_payload)
    assert registration_response.status_code == 201, "Expected status code 201 for successful registration."

    stmt = select(User).where(User.email == registration_payload["email"])
    result = await db_session_commit.execute(stmt)
    created_user = result.scalars().first()
    assert created_user is not None, "User should be created in the database."

    stmt_token = select(ActivationToken).where(ActivationToken.user_id == created_user.id)
    result_token = await db_session_commit.execute(stmt_token)
    activation_token = result_token.scalars().first()
    assert activation_token is not None, "Activation token should be created in the database."

    activation_response = await client.get(
        f"/api/v1/accounts/activate/{activation_token.token}/"
    )
    assert activation_response.status_code == 200, "Expected status code 200 for successful activation."

    await db_session_commit.refresh(created_user)
    assert created_user.is_active, "User should be active after successful activation."

    reset_request_response = await client.post(
        "/api/v1/accounts/forgot-password/",
        json={"email": registration_payload["email"]}
    )
    assert reset_request_response.status_code == 200, "Expected status code 200 for password reset token request."

    stmt_reset = select(PasswordResetToken).where(PasswordResetToken.user_id == created_user.id)
    result_reset = await db_session_commit.execute(stmt_reset)
    reset_token_record = result_reset.scalars().first()
    assert reset_token_record is not None, "Password reset token should be created in the database."

    new_password = "NewTest1234!"
    reset_response = await client.post(
        f"/api/v1/accounts/reset-password/{reset_token_record.token}/",
        json={"new_password": new_password, "confirm_password": new_password}
    )
    assert reset_response.status_code == 200, "Expected status code 200 for successful password reset."
    assert reset_response.json()["message"] == "Password reset successfully.", (
        "Unexpected response message for password reset."
    )

    await db_session_commit.refresh(created_user)
    assert created_user.verify_password(new_password), "Password should be updated successfully in the database."


@pytest.mark.asyncio
async def test_reset_password_invalid_email(client, db_session):
    """
    Test password reset with an email that does not exist in the database.

    Validates that the endpoint returns a 400 status code and appropriate error message.
    """
    reset_payload = {
        "new_password": "NewTest1234!",
        "confirm_password": "NewTest1234!"
    }

    response = await client.post("/api/v1/accounts/reset-password/random_token/", json=reset_payload)

    assert response.status_code == 400, "Expected status code 400 for invalid email."
    assert response.json()["detail"] == "Invalid or expired password reset token.", "Unexpected error message."


@pytest.mark.asyncio
async def test_reset_password_invalid_token(client, db_session, seed_user_groups):
    """
    Test password reset with an incorrect token.

    Validates that the endpoint returns a 400 status code and an appropriate error message when an invalid token is provided.
    Also ensures that any invalid token is removed from the database.
    """
    registration_payload = {
        "email": "invalid_token_testuser@example.com",
        "password": "Test1234!"
    }
    response = await client.post("/api/v1/accounts/register/", json=registration_payload)
    assert response.status_code == 201, "User registration failed."

    query_user = select(User).where(User.email == registration_payload["email"])
    result_user = await db_session.execute(query_user)
    user = result_user.scalars().first()
    assert user is not None, "User should exist in the database."

    user_id = user.id

    user.is_active = True
    await db_session.commit()

    reset_request_payload = {"email": registration_payload["email"]}
    response = await client.post("/api/v1/accounts/forgot-password/", json=reset_request_payload)
    assert response.status_code == 200, "Password reset request failed."

    reset_complete_payload = {
        "new_password": "NewTest1234!",
        "confirm_password": "NewTest1234!"
    }
    invalid_token = "some_completely_wrong_token"
    response = await client.post(f"/api/v1/accounts/reset-password/{invalid_token}/", json=reset_complete_payload)
    assert response.status_code == 400, "Expected status code 400 for invalid token."
    assert response.json()["detail"] == "Invalid or expired password reset token.", "Unexpected error message."

    query_token = select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    result_token = await db_session.execute(query_token)
    token_record = result_token.scalars().first()
    assert token_record is None, "The original valid token should still exist in the DB."
