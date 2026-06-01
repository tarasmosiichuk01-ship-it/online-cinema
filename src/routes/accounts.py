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
    status_code=status.HTTP_201_CREATED
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
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

@router.get("/activate/{token}/", response_model=MessageResponseSchema, status_code=status.HTTP_200_OK)
async def activate_token(
    token: str,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
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
    status_code=status.HTTP_200_OK
)
async def reset_activation_token(
    user_data: ResetActivationSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
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

    return MessageResponseSchema(message="If you are registered and not yet activated, you will receive an email.")


@router.post(
    "/login/",
    response_model=UserLoginResponseSchema,
    status_code=status.HTTP_200_OK
)
async def login_user(
    login_data: UserLoginRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    settings: BaseAppSettings = Depends(get_settings),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager)
):
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


@router.post("/logout/", response_model=MessageResponseSchema, status_code=status.HTTP_200_OK)
async def logout_user(
    logout_data: UserLogoutRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
):
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
    status_code=status.HTTP_200_OK
)
async def update_access_token(
    token_data: TokenRefreshRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
):
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


@router.post("/change-password/", response_model=MessageResponseSchema, status_code=status.HTTP_200_OK)
async def change_password(
    user_data: ChangePasswordRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db),

):
    if user_data.new_password != user_data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")

    if not current_user.verify_password(user_data.old_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password")

    if user_data.old_password == user_data.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different from old password")
    try:
        current_user.password = user_data.new_password

        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == current_user.id)
        )
        await db.commit()

    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while changing password.")

    return MessageResponseSchema(message="Successfully changed password.")

@router.post(
    "/forgot-password/",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK
)
async def forgot_password(
    user_data: ForgotPasswordRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
):
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
    status_code=status.HTTP_200_OK
)
async def reset_password(
    token: str,
    user_data: ResetPasswordRequestSchema,
    db: AsyncSession = Depends(get_postgresql_db),
):
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")

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
