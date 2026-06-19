from datetime import datetime, timezone

from sqlalchemy import ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="cart")

    cart_items: Mapped[list["CartItem"]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), nullable=False)
    cart: Mapped["Cart"] = relationship("Cart", back_populates="cart_items")

    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), nullable=False)
    movie: Mapped["Movie"] = relationship("Movie", back_populates="cart_items")

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("cart_id", "movie_id", name="unique_cart_item_constraint"),
    )


class PurchasedMovie(Base):
    __tablename__ = "user_purchased_movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="purchased_movies")

    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), nullable=False)
    movie: Mapped["Movie"] = relationship("Movie", back_populates="purchased_movies")

    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="unique_user_movie_purchase"),
    )
