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



