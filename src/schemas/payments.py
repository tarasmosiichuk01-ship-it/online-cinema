import decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.payments import PaymentStatusEnum


class GenreShortResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class MovieShortResponseSchema(BaseModel):
    id: int
    name: str
    genres: list[GenreShortResponseSchema]

    model_config = ConfigDict(from_attributes=True)


class PaymentCreateSchema(BaseModel):
    order_id: int

    model_config = ConfigDict(from_attributes=True)


class StripeSessionResponseSchema(BaseModel):
    session_id: str
    checkout_url: str

    model_config = ConfigDict(from_attributes=True)


class PaymentItemResponseSchema(BaseModel):
    id: int
    order_item_id: int
    price_at_payment: decimal.Decimal
    movie: MovieShortResponseSchema

    model_config = ConfigDict(from_attributes=True)


class PaymentResponseSchema(BaseModel):
    id: int
    order_id: int
    amount: decimal.Decimal
    status: PaymentStatusEnum
    created_at: datetime
    payment_items: list[PaymentItemResponseSchema]

    model_config = ConfigDict(from_attributes=True)
