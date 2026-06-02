import decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CartItemCreateSchema(BaseModel):
    movie_id: int


class GenreShortResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)

