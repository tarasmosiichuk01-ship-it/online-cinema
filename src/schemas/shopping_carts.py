import decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CartItemCreateSchema(BaseModel):
    movie_id: int
