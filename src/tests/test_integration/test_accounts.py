from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models.accounts import User, ActivationToken


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
