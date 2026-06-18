import datetime
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status, Query, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.settings import settings, Settings
from config.database import get_postgresql_db
from models.accounts import User, UserGroupEnum
from models.orders import OrderStatusEnum
from models.payments import PaymentStatusEnum
from notifications.emails import EmailSender
from notifications.interfaces import EmailSenderInterface
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_settings() -> Settings:
    """
    Returns the application settings instance.

    Used as a FastAPI dependency to inject settings
    into route handlers and other dependencies.
    """
    return settings

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_postgresql_db),
) -> User:
    """
    Retrieves the currently authenticated user from the JWT access token.

    Decodes the JWT token, extracts the user_id, and fetches the
    corresponding user from the database. Raises HTTP 401 if the token
    is invalid or the user is not found. Raises HTTP 403 if the user
    account is inactive.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY_ACCESS,
            algorithms=[settings.JWT_SIGNING_ALGORITHM],
        )

        user_id = payload.get("user_id")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    query = select(User).options(joinedload(User.group)).where(User.id == int(user_id))
    result = await db.execute(query)
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user.",
        )

    return user

async def get_moderator_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Validates that the current user has Moderator or Admin role.

    Raises HTTP 403 if the current user does not have the required role.
    Used to protect moderator-only endpoints.
    """
    if not current_user.has_group(UserGroupEnum.MODERATOR) and not current_user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden. Moderator or Admin role required."
        )

    return current_user

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Validates that the current user has Admin role.

    Raises HTTP 403 if the current user does not have the Admin role.
    Used to protect admin-only endpoints.
    """
    if not current_user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden. Admin role required."
        )

    return current_user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_postgresql_db)
) -> User | None:
    """
    Attempts to retrieve the currently authenticated user from the request.

    Unlike get_current_user, this dependency does not raise an exception
    if the token is missing or invalid — it returns None instead.
    Used for endpoints that support both authenticated and anonymous access.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY_ACCESS,
            algorithms=[settings.JWT_SIGNING_ALGORITHM],
        )
        user_id = payload.get("user_id")
        if user_id is None:
            return None

    except JWTError:
        return None

    query = select(User).options(joinedload(User.group)).where(User.id == int(user_id))
    result = await db.execute(query)
    user = result.scalars().first()

    if user is None or not user.is_active:
        return None

    return user


def get_accounts_email_notificator() -> EmailSenderInterface:
    """
    Creates and returns an EmailSender instance configured with
    application settings.

    Used as a FastAPI dependency to inject the email sender
    into route handlers that need to send emails.
    """
    return EmailSender(
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        email=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        template_dir=settings.PATH_TO_EMAIL_TEMPLATES_DIR,
        activation_email_template_name=settings.ACTIVATION_EMAIL_TEMPLATE_NAME,
        activation_complete_email_template_name=settings.ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME,
        password_email_template_name=settings.PASSWORD_RESET_TEMPLATE_NAME,
        reply_comment_template_name=settings.REPLY_COMMENT_TEMPLATE_NAME,
        reaction_comment_template_name=settings.REACTION_COMMENT_TEMPLATE_NAME,
        confirmation_payment_template_name=settings.CONFIRMATION_PAYMENT_TEMPLATE_NAME,
    )


def get_jwt_auth_manager(settings: Settings = Depends(get_settings)) -> JWTAuthManagerInterface:
    """
    Creates and returns a JWTAuthManager instance configured with
    application settings.

    Used as a FastAPI dependency to inject the JWT manager
    into route handlers that need to create or validate tokens.
    """
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )


def get_query_params(
    search: Optional[str] = Query(None, description="Search by name, description, star or director"),
    release_year: Optional[int] = Query(None, description="Filter by year"),
    min_rating_imdb: Optional[float] = Query(None, description="Filter by IMDb rating"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    sort_by: str = Query("id", description="Sort field: id, year, price, votes"),
    order: str = Query("desc", description="Direction: asc (growing) or desc (falling)"),
):
    """
    Collects and returns common query parameters for movie list filtering,
    searching and sorting.

    Used as a FastAPI dependency in endpoints that support
    filtering and sorting of movie lists.
    """
    return {
        "search": search,
        "release_year": release_year,
        "min_rating_imdb": min_rating_imdb,
        "genre": genre,
        "sort_by": sort_by,
        "order": order,
    }

def admin_query_params(
    user_id: Optional[int] = Query(None, description="Filter by user id"),
    start_date: Optional[datetime.date] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime.date] = Query(None, description="Filter by end date"),
    order_status: Optional[OrderStatusEnum] = Query(None, description="Filter by order status"),
    payment_status: Optional[PaymentStatusEnum] = Query(None, description="Filter by payment status")
):
    """
    Collects and returns query parameters for admin filtering of orders
    and payments by user, date range and status.

    Used as a FastAPI dependency in admin endpoints that support
    filtering of orders and payments.
    """
    return {
        "user_id": user_id,
        "start_date": start_date,
        "end_date": end_date,
        "order_status": order_status,
        "payment_status": payment_status,
    }
