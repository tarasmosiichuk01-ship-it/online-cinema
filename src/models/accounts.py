import enum
import secrets
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List

from sqlalchemy import Integer, Enum, String, Boolean, DateTime, func, ForeignKey, Date, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.validators import accounts as validators
from src.models.base import Base
from src.security.passwords import hash_password, verify_password


class UserGroupEnum(str, enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class GenderEnum(str, enum.Enum):
    MAN = "man"
    WOMAN = "woman"


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[UserGroupEnum] = mapped_column(Enum(UserGroupEnum), nullable=False, unique=True)

    users: Mapped[List["User"]] = relationship("User", back_populates="group")

    def __repr__(self):
        return f"<UserGroup(id={self.id}, name={self.name})>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    _hashed_password: Mapped[str] = mapped_column("hashed_password", String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    group_id: Mapped[int] = mapped_column(ForeignKey("user_groups.id", ondelete="RESTRICT"), nullable=False)
    group: Mapped["UserGroup"] = relationship("UserGroup", back_populates="users")

    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    activation_token: Mapped[Optional["ActivationToken"]] = relationship(
        "ActivationToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    password_reset_token: Mapped[Optional["PasswordResetToken"]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    movie_comments: Mapped[list["MovieComment"]] = relationship(
        "MovieComment", back_populates="user"
    )

    comment_reactions: Mapped[list["CommentReaction"]] = relationship(
        "CommentReaction",
        back_populates="user"
    )

    movie_reactions: Mapped[list["MovieReaction"]] = relationship(
        "MovieReaction", back_populates="user"
    )

    movie_ratings: Mapped[list["MovieRating"]] = relationship(
        "MovieRating", back_populates="user"
    )

    movie_favourites: Mapped[list["MovieFavourite"]] = relationship(
        "MovieFavourite", back_populates="user"
    )

    cart: Mapped["Cart"] = relationship("Cart", back_populates="user", uselist=False)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, is_active={self.is_active})>"

    def has_group(self, group_name: UserGroupEnum) -> bool:
        return self.group.name == group_name

    @classmethod
    def create(cls, email: str, raw_password: str, group_id: int | Mapped[int]) -> "User":

        user = cls(email=email, group_id=group_id)
        user.password = raw_password
        return user

    @property
    def password(self) -> None:
        raise AttributeError("Password is write-only. Use the setter to set the password.")

    @password.setter
    def password(self, raw_password: str) -> None:
        validators.validate_password_strength(raw_password)
        self._hashed_password = hash_password(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        return verify_password(raw_password, self._hashed_password)

    @validates("email")
    def validate_email(self, key, value):
        return validators.validate_email(value.lower())


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar: Mapped[Optional[str]] = mapped_column(String(255))
    gender: Mapped[Optional[GenderEnum]] = mapped_column(Enum(GenderEnum))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    info: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[User] = relationship("User", back_populates="profile")


    def __repr__(self):
        return (
            f"<UserProfile(id={self.id}, first_name={self.first_name}, last_name={self.last_name}, "
            f"gender={self.gender}, date_of_birth={self.date_of_birth})>"
        )

class TokenBase(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=1)
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

class ActivationToken(TokenBase):
    __tablename__ = "activation_tokens"
    __table_args__ = (UniqueConstraint("user_id"),)

    user: Mapped[User] = relationship("User", back_populates="activation_token")

    def __repr__(self):
        return f"<ActivationToken(id={self.id}, token={self.token}, expires_at={self.expires_at})>"

class PasswordResetToken(TokenBase):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("user_id"),)

    user: Mapped[User] = relationship("User", back_populates="password_reset_token")


    def __repr__(self):
        return f"<PasswordResetToken(id={self.id}, token={self.token}, expires_at={self.expires_at})>"


class RefreshToken(TokenBase):
    __tablename__ = "refresh_tokens"

    token: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32)
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")

    @classmethod
    def create(cls, user_id: int | Mapped[int], days_valid: int, token: str) -> "RefreshToken":
        expires_at = datetime.now(timezone.utc) + timedelta(days=days_valid)

        return cls(user_id=user_id, expires_at=expires_at, token=token)

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, token={self.token}, expires_at={self.expires_at})>"
