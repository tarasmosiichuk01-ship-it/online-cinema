import decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.payments import PaymentStatusEnum


class GenreShortResponseSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)



