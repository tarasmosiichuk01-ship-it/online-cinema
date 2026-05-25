import decimal
from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GenreSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class StarSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class DirectorSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class CertificationSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class MovieBaseSchema(BaseModel):
    name: str = Field(..., max_length=100)
    year: int
    time: int = Field(..., ge=0)
    imdb: float = Field(..., ge=0)
    votes: int = Field(..., ge=0)
    meta_score: float = Field(..., ge=0, le=10)
    gross: float = Field(..., ge=0)
    description: str
    price: decimal.Decimal = Field(..., ge=0)

    model_config = {"from_attributes": True}

    @field_validator("year")
    @classmethod
    def validate_year(cls, value):
        current_year = datetime.now().year
        if value.year > current_year + 1:
            raise ValueError(f"The year in 'year' cannot be greater than {current_year + 1}.")
        return value


class MovieDetailSchema(MovieBaseSchema):
    id: int
    uuid: UUID
    certification: CertificationSchema
    genres: List[GenreSchema]
    stars: List[StarSchema]
    directors: List[DirectorSchema]

    model_config = {"from_attributes": True}
