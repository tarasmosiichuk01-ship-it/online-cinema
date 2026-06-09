import decimal
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, DateTime, func, Enum, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

class PaymentStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    CANCELED = "CANCELED"
    REFUNDED = "REFUNDED"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="payments")

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(PaymentStatusEnum),
        nullable=False,
        default=PaymentStatusEnum.PENDING
    )

    amount: Mapped[decimal.Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False
    )

    external_payment_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    payment_intent_id: Mapped[Optional[str]] = mapped_column(nullable=True)

    payment_items: Mapped[list["PaymentItem"]] = relationship("PaymentItem", back_populates="payment")


class PaymentItem(Base):
    __tablename__ = "payment_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False)
    payment: Mapped["Payment"] = relationship("Payment", back_populates="payment_items")

    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"), nullable=False)
    order_item: Mapped["OrderItem"] = relationship("OrderItem", back_populates="payment_items")

    price_at_payment: Mapped[decimal.Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False
    )
