from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.dependencies import get_accounts_email_notificator
from database import get_postgresql_db
from notifications.interfaces import EmailSenderInterface
from schemas.accounts import UserRegistrationRequestSchema, UserRegistrationResponseSchema, MessageResponseSchema, \
    ResetActivationSchema
from models.accounts import User, UserGroup, UserGroupEnum, ActivationToken

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

    activation_link = f"http://127.0.0.1:8000/api/v1/auth/activate/{activation_token.token}"

    await email_sender.send_activation_email(
        new_user.email,
        activation_link
    )

    return UserRegistrationResponseSchema.model_validate(new_user)

@router.get("/activate/{token}", response_model=MessageResponseSchema, status_code=status.HTTP_200_OK)
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

    activation_link = f"http://127.0.0.1:8000/api/v1/auth/activate/{new_activation_token.token}"

    await email_sender.send_activation_email(
        user.email,
        activation_link
    )

    return MessageResponseSchema(message="If you are registered and not yet activated, you will receive an email.")

