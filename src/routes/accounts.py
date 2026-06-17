from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.dependencies import get_accounts_email_notificator, get_jwt_auth_manager, get_settings, get_current_user
from config.settings import BaseAppSettings
from config.database import get_postgresql_db
from exceptions.security import BaseSecurityError
from notifications.interfaces import EmailSenderInterface
from schemas.accounts import UserRegistrationRequestSchema, UserRegistrationResponseSchema, MessageResponseSchema, \
    ResetActivationSchema, UserLoginResponseSchema, UserLoginRequestSchema, UserLogoutRequestSchema, \
    TokenRefreshResponseSchema, TokenRefreshRequestSchema, ChangePasswordRequestSchema, ForgotPasswordRequestSchema, \
    ResetPasswordRequestSchema
from models.accounts import User, UserGroup, UserGroupEnum, ActivationToken, RefreshToken, PasswordResetToken
from security.interfaces import JWTAuthManagerInterface


router = APIRouter()


@router.post(
    "/register/",
    response_model=UserRegistrationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "<h3>This endpoint handles new user registration. "
        "It checks if the email is already in use, assigns the default 'USER' group, "
        "hashes the password, creates an activation token, and stores the user in the database. "
        "Upon successful creation, an activation email with a unique verification link is sent to the user.</h3>"
    ),
    responses={
        409: {
            "description": "Email already exists.",
            "content": {
                "application/json": {
                    "example": {"detail": "A user with this email user@example.com already exists."}
                }
            }
        },
        500: {
            "description": "Internal server error due to missing configurations or database failures.",
            "content": {
                "application/json": {
                    "example": {"detail": "Default user group not found."}
                }
            }
        }
    }
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
    """
    Register a new system user and trigger an activation email (asynchronously).

    This function performs database validation to ensure uniqueness of the email.
    It links the new user to the default 'USER' group, creates a corresponding
    activation token transactionally, and sends a generated activation link via
    the provided email notification service.

    :param user_data: Request body containing registration details (email and password).
    :type user_data: UserRegistrationRequestSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param email_sender: The email notification sender service component.
    :type email_sender: EmailSenderInterface

    :return: A response containing the created user profile metadata.
    :rtype: UserRegistrationResponseSchema

    :raises HTTPException: Raises a 409 error if the email is already registered.
    :raises HTTPException: Raises a 500 error if the default user group is missing in DB
                           or if a database transaction failure occurs during user creation.
    """
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with this email {user_data.email} already exists."
        )

    query = select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    result = await db.execute(query)
    user_group = result.scalars().first()

    if not user_group:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user group not found."
        )

    try:
        new_user = User.create(
            email=str(user_data.email),
            raw_password=user_data.password,
            group_id=user_group.id,
        )
        db.add(new_user)
        await db.flush()

        activation_token = ActivationToken(user_id=new_user.id)
        db.add(activation_token)

        await db.commit()
        await db.refresh(new_user)
        await db.refresh(activation_token)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during user creation."
        )

    activation_link = f"http://127.0.0.1:8000/api/v1/activate/{activation_token.token}/"

    await email_sender.send_activation_email(
        new_user.email,
        activation_link
    )

    return UserRegistrationResponseSchema.model_validate(new_user)


@router.get(
    "/activate/{token}/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Activate a user account",
    description=(
        "<h3>This endpoint activates a user's account using a unique activation token. "
        "It validates the token's existence, checks if it has expired, and verifies if the account "
        "is already active. Upon successful validation, the user's status is updated to active, "
        "the token is consumed (deleted), and a confirmation email is dispatched.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to invalid, expired token, or already active account.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid or expired activation token."}
                }
            },
        }
    }
)
async def activate_token(
    token: str,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
    """
    Activate a user account via a verification token (asynchronously).

    This function fetches the activation token along with the associated user,
    verifies its expiration status, and updates the user's `is_active` flag to True.
    After activation, the token record is deleted from the database to prevent reuse,
    and a success notification email is triggered.

    :param token: The unique activation token string extracted from the path URL.
    :type token: str
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param email_sender: The email notification sender service component.
    :type email_sender: EmailSenderInterface

    :return: A message response confirming successful account activation.
    :rtype: MessageResponseSchema

    :raises HTTPException: Raises a 400 error if the token is not found, has expired,
                           or if the user account is already activated.
    """
    query = (
        select(ActivationToken)
        .options(joinedload(ActivationToken.user))
        .where(ActivationToken.token == token)
    )
    result = await db.execute(query)
    token_record = result.scalars().first()

    if not token_record:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired activation token."
        )

    expires_at = token_record.expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(tz=timezone.utc):
        await db.delete(token_record)
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired activation token."
        )

    user = token_record.user

    if user.is_active:
        await db.delete(token_record)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is already active."
        )

    user.is_active = True
    await db.delete(token_record)
    await db.commit()


    login_link = "http://127.0.0.1/accounts/login/"

    await email_sender.send_activation_complete_email(
        email=user.email,
        login_link=login_link
    )

    return MessageResponseSchema(message="User account activated successfully.")


@router.post(
    "/reset-activation/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Resend or reset user activation token",
    description=(
        "<h3>This endpoint handles resetting or regenerating an activation token for inactive users. "
        "If a user with the provided email exists and is not yet activated, any old tokens are deleted, "
        "a new unique activation token is generated, and a fresh activation email is sent. "
        "To prevent user enumeration attacks, the endpoint always returns a generic success message "
        "regardless of whether the email exists or is already active.</h3>"
    ),
    responses={
        500: {
            "description": "Internal server error due to database transaction failure.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred. Please try again later."}
                }
            },
        }
    }
)
async def reset_activation_token(
    user_data: ResetActivationSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
    """
    Reset and resend a user activation token (asynchronously).

    This function safely regenerates an account verification link. It searches for the user by email,
    ensures the user is not already active, flushes old tokens transactionally, creates a new token,
    and dispatches an email notification. It applies security best practices by hiding the true
    existence of accounts via consistent generic responses.

    :param user_data: Request body containing the target email address for token re-issuance.
    :type user_data: ResetActivationSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param email_sender: The email notification sender service component.
    :type email_sender: EmailSenderInterface

    :return: A generic success message confirming that an email will be sent if conditions are met.
    :rtype: MessageResponseSchema

    :raises HTTPException: Raises a 500 error if a database exception occurs during token modification.
    """
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or user.is_active:
        return MessageResponseSchema(
            message="If you are registered, you will receive an email with instructions."
        )

    try:
        await db.execute(delete(ActivationToken).where(ActivationToken.user_id == user.id))

        new_activation_token = ActivationToken(user_id=user.id)
        db.add(new_activation_token)
        await db.commit()
        await db.refresh(new_activation_token)
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred. Please try again later."
        )

    activation_link = f"http://127.0.0.1:8000/api/v1/activate/{new_activation_token.token}/"

    await email_sender.send_activation_email(
        user.email,
        activation_link
    )

    return MessageResponseSchema(
        message="If you are registered and not yet activated, you will receive an email."
    )


@router.post(
    "/login/",
    response_model=UserLoginResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and generate JWT tokens",
    description=(
        "<h3>This endpoint authenticates a user using their email and password. "
        "It validates user credentials, ensures that the account has been activated, "
        "and generates both a JWT Access Token and a JWT Refresh Token. "
        "The generated refresh token is transactionally stored in the database for session tracking.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to invalid email or password.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid email or password."}
                }
            },
        },
        403: {
            "description": "Forbidden because the user account is not active.",
            "content": {
                "application/json": {
                    "example": {"detail": "User account is not activated."}
                }
            },
        },
        500: {
            "description": "Internal server error due to database transaction failure.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while processing the request."}
                }
            },
        }
    }
)
async def login_user(
    login_data: UserLoginRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    settings: BaseAppSettings = Depends(get_settings),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager)
):
    """
    Authenticate a user and issue JWT credentials (asynchronously).

    This function searches for a user by email, verifies the hashed password,
    and checks if the account is activated. If validation passes, it creates
    a fresh JWT refresh token, writes it to the database using configured expiration settings,
    and returns a pair of access and refresh tokens to the client.

    :param login_data: Request body containing user credentials (email and password).
    :type login_data: UserLoginRequestSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param settings: Global application settings for token lifespan configuration.
    :type settings: BaseAppSettings
    :param jwt_manager: Component responsible for encoding and signing JWT tokens.
    :type jwt_manager: JWTAuthManagerInterface

    :return: A schema object containing the access and refresh tokens.
    :rtype: UserLoginResponseSchema

    :raises HTTPException: Raises a 401 error if credentials are incorrect.
    :raises HTTPException: Raises a 403 error if the user account is inactive.
    :raises HTTPException: Raises a 500 error if saving the refresh token to the DB fails.
    """
    query = select(User).where(User.email == login_data.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not user.verify_password(login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not activated.",
        )

    jwt_refresh_token = jwt_manager.create_refresh_token({"user_id": user.id})

    try:
        refresh_token = RefreshToken.create(
            user_id=user.id,
            days_valid=settings.LOGIN_TIME_DAYS,
            token=jwt_refresh_token
        )
        db.add(refresh_token)
        await db.flush()
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request.",
        )

    jwt_access_token = jwt_manager.create_access_token({"user_id": user.id})
    return UserLoginResponseSchema(
        access_token=jwt_access_token,
        refresh_token=jwt_refresh_token,
    )


@router.post(
    "/logout/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Logout user and invalidate refresh token",
    description=(
        "<h3>This endpoint logs out a user by invalidating their active session. "
        "It looks up the provided JWT Refresh Token in the database and, if found, "
        "permanently deletes the token record. This ensures the refresh token "
        "cannot be used again to obtain new access tokens.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to an invalid or missing refresh token.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid refresh token."}
                }
            },
        },
        500: {
            "description": "Internal server error due to a database failure during token deletion.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while processing the request."}
                }
            },
        }
    }
)
async def logout_user(
    logout_data: UserLogoutRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
):
    """
    Log out the user by revoking their refresh token (asynchronously).

    This function handles the termination of a user's session. It verifies the existence
    of the provided refresh token in the database, removes the token record transactionally
    to prevent reuse, and commits the changes.

    :param logout_data: Request body containing the refresh token to be revoked.
    :type logout_data: UserLogoutRequestSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A message response confirming successful logout.
    :rtype: MessageResponseSchema

    :raises HTTPException: Raises a 400 error if the refresh token is invalid or not found.
    :raises HTTPException: Raises a 500 error if a database exception occurs during token deletion.
    """
    query = select(RefreshToken).where(RefreshToken.token == logout_data.refresh_token)
    result = await db.execute(query)
    token = result.scalars().first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token.",
        )

    try:
        await db.delete(token)
        await db.commit()

    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request.",
        )

    return MessageResponseSchema(message="Successfully logged out.")


@router.post(
    "/refresh/",
    response_model=TokenRefreshResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token using a refresh token",
    description=(
        "<h3>This endpoint issues a new JWT Access Token to the client. "
        "It validates the provided JWT Refresh Token structure, checks its presence "
        "and validity in the database, verifies the associated user's existence, "
        "and returns a newly generated short-lived access token.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to token decoding or signature validation failure.",
            "content": {
                "application/json": {
                    "example": {"detail": "Token signature has expired."}
                }
            },
        },
        401: {
            "description": "Unauthorized because the refresh token does not exist in the database.",
            "content": {
                "application/json": {
                    "example": {"detail": "Refresh token not found."}
                }
            },
        },
        404: {
            "description": "Not Found if the user linked to the token no longer exists.",
            "content": {
                "application/json": {
                    "example": {"detail": "User not found."}
                }
            },
        }
    }
)
async def update_access_token(
    token_data: TokenRefreshRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
):
    """
    Renew a short-lived JWT access token (asynchronously).

    This function decodes and validates the incoming refresh token payload using the security manager.
    It performs cross-checks against the stored database session tokens and confirms the user account
    still exists before minting and returning a fresh access token.

    :param token_data: Request body containing the active refresh token.
    :type token_data: TokenRefreshRequestSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param jwt_manager: Component responsible for decoding, signing, and managing JWT tokens.
    :type jwt_manager: JWTAuthManagerInterface

    :return: A response schema containing the new JWT access token.
    :rtype: TokenRefreshResponseSchema

    :raises HTTPException: Raises a 400 error if token decoding fails (expired, invalid structure).
    :raises HTTPException: Raises a 401 error if the token is revoked or missing from the DB.
    :raises HTTPException: Raises a 404 error if the token's user payload references a non-existent account.
    """
    try:
        decoded_token = jwt_manager.decode_refresh_token(token_data.refresh_token)
        user_id = decoded_token.get("user_id")
    except BaseSecurityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error)
        )

    query = select(RefreshToken).filter_by(token=token_data.refresh_token)
    result = await db.execute(query)
    refresh_token_record = result.scalars().first()
    if not refresh_token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )

    query = select(User).filter_by(id=user_id)
    result = await db.execute(query)
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    new_access_token = jwt_manager.create_access_token({"user_id": user_id})

    return TokenRefreshResponseSchema(access_token=new_access_token)


@router.post(
    "/change-password/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Change user password and revoke sessions",
    description=(
        "<h3>This endpoint allows an authenticated user to change their password. "
        "It validates that the new password matches the confirmation, verifies the user's "
        "current password, and ensures the new password is different from the old one. "
        "Upon a successful password change, all active refresh tokens (sessions) for this user "
        "are permanently deleted from the database to enforce re-authentication across all devices.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to mismatched passwords, incorrect old password, or identical old and new passwords.",
            "content": {
                "application/json": {
                    "example": {"detail": "New passwords do not match"}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        500: {
            "description": "Internal server error due to database transaction failure during update or session revocation.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while changing password."}
                }
            },
        }
    }
)
async def change_password(
    user_data: ChangePasswordRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db),

):
    """
    Change the current user's password and invalidate all active sessions (asynchronously).

    This function performs strict validation on the old and new passwords provided in the request.
    If all business logic checks pass, the user's password record is updated, and all associated
    refresh tokens are deleted transactionally to guarantee absolute security logout across all platforms.

    :param user_data: Request body containing old, new, and confirmation passwords.
    :type user_data: ChangePasswordRequestSchema
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A message response confirming successful password modification.
    :rtype: MessageResponseSchema

    :raises HTTPException: Raises a 400 error if new passwords mismatch, the old password is invalid,
                           or the new password is identical to the old one.
    :raises HTTPException: Raises a 500 error if the database fails to update the user or purge tokens.
    """
    if user_data.new_password != user_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )

    if not current_user.verify_password(user_data.old_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    if user_data.old_password == user_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from old password"
        )

    try:
        current_user.password = user_data.new_password

        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == current_user.id)
        )
        await db.commit()

    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while changing password."
        )

    return MessageResponseSchema(message="Successfully changed password.")


@router.post(
    "/forgot-password/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Initiate user password reset process",
    description=(
        "<h3>This endpoint initiates the password recovery process for a user. "
        "If an account with the provided email exists and is active, any previous password reset tokens "
        "are deleted, a new unique token is generated, and a reset link is emailed to the user. "
        "To mitigate user enumeration attacks, the endpoint always returns a generic success message, "
        "masking whether the email exists or is active in the system.</h3>"
    ),
    responses={
        500: {
            "description": "Internal server error due to database transaction failure during token generation.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred. Please try again later."}
                }
            },
        }
    }
)
async def forgot_password(
    user_data: ForgotPasswordRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
):
    """
    Generate a password reset token and email the recovery link (asynchronously).

    This function processes password recovery requests securely. It screens the incoming email address,
    verifies that the user exists and is fully activated, clears stale tokens transactionally, issues
    a fresh recovery token, and dispatches a notification email. Generic response messaging is utilized
    to preserve user privacy and prevent account harvesting.

    :param user_data: Request body containing the target email address for password recovery.
    :type user_data: ForgotPasswordRequestSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param email_sender: The email notification sender service component.
    :type email_sender: EmailSenderInterface

    :return: A generic message response indicating that a recovery link will be sent if conditions are met.
    :rtype: MessageResponseSchema

    :raises HTTPException: Raises a 500 error if a database exception occurs during token cleanup or addition.
    """
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not user.is_active:
        return MessageResponseSchema(
            message="If you wish to reset your password, you will receive an email."
        )

    try:
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))

        new_reset_token = PasswordResetToken(user_id=user.id)
        db.add(new_reset_token)
        await db.commit()
        await db.refresh(new_reset_token)

    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred. Please try again later."
        )

    reset_link = f"http://127.0.0.1:8000/api/v1/reset-password/{new_reset_token.token}/"

    await email_sender.send_password_reset_email(email=user_data.email, reset_link=reset_link)

    return MessageResponseSchema(
        message="If you wish to reset your password, you will receive an email."
    )

@router.post(
    "/reset-password/{token}/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Reset user password using a recovery token",
    description=(
        "<h3>This endpoint completes the password recovery process. "
        "It validates the unique token from the URL path, checks its expiration status, "
        "and ensures that the new password matches the confirmation password. "
        "Upon successful validation, the user's password is updated, and the used token "
        "is permanently removed from the database to prevent reuse.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to an invalid/expired token or mismatched passwords.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid or expired password reset token."}
                }
            },
        },
        500: {
            "description": "Internal server error due to database transaction failure during password update.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while resetting the password."}
                }
            },
        }
    }
)
async def reset_password(
    token: str,
    user_data: ResetPasswordRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
):
    """
    Reset user password via a valid recovery token (asynchronously).

    This function securely applies a new password to a user account. It fetches the recovery token,
    verifies its active lifespan, and validates that the submission payloads contain matching passwords.
    The update and the token deletion are executed inside a single database transaction.

    :param token: The unique password reset token extracted from the path URL.
    :type token: str
    :param user_data: Request body containing the new password and confirmation string.
    :type user_data: ResetPasswordRequestSchema
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A message response confirming successful password modification.
    :rtype: MessageResponseSchema

    :raises HTTPException: Raises a 400 error if the token is invalid, expired, or if the new passwords do not match.
    :raises HTTPException: Raises a 500 error if a database exception occurs during password persistence.
    """
    query = (
        select(PasswordResetToken)
        .options(joinedload(PasswordResetToken.user))
        .where(PasswordResetToken.token == token)
    )
    result = await db.execute(query)
    token_record = result.scalars().first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )

    expires_at = token_record.expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(tz=timezone.utc):
        await db.delete(token_record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )

    if user_data.new_password != user_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )

    user = token_record.user

    try:
        user.password = user_data.new_password
        await db.delete(token_record)
        await db.commit()

    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting the password."
        )

    return MessageResponseSchema(message="Password reset successfully.")
