import decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CartItemCreateSchema(BaseModel):
    movie_id: int


class GenreShortResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class CartItemMovieSchema(BaseModel):
    name: str
    price: decimal.Decimal
    genres: list[GenreShortResponseSchema]
    year: int

    model_config = ConfigDict(from_attributes=True)


class CartItemResponseSchema(BaseModel):
    id: int
    cart_id: int
    added_at: datetime
    movie: CartItemMovieSchema

    model_config = ConfigDict(from_attributes=True)


class CartResponse(BaseModel):
    id: int
    user_id: int
    cart_items: list[CartItemResponseSchema]

    model_config = ConfigDict(from_attributes=True)