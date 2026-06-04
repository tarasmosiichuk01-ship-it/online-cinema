from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.orders import OrderStatusEnum


class GenreShortResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class MovieShortResponseSchema(BaseModel):
    id: int
    name: str
    genres: list[GenreShortResponseSchema]

    model_config = ConfigDict(from_attributes=True)


class OrderItemResponseSchema(BaseModel):
    id: int
    order_id: int
    movie_id: int
    movie: MovieShortResponseSchema

    model_config = ConfigDict(from_attributes=True)


class OrderResponseSchema(BaseModel):
    id: int
    user_id: int
    status: OrderStatusEnum
    created_at: datetime
    order_items: list[OrderItemResponseSchema]

    model_config = ConfigDict(from_attributes=True)
