from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models.accounts import User, ActivationToken


@pytest.mark.asyncio
async def test_register_user_success(client, db_session):
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