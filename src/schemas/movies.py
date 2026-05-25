import decimal
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class GenreBaseSchema(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)


class GenreListItemSchema(GenreBaseSchema):
    pass


class GenreCreateShema(GenreBaseSchema):
    pass


class GenreUpdateShema(GenreBaseSchema):
    pass


class GenreResponseSchema(GenreBaseSchema):
    id: int


class StarSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class DirectorSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class CertificationSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)

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
    genres: List[GenreListItemSchema]
    stars: List[StarSchema]
    directors: List[DirectorSchema]

    model_config = ConfigDict(from_attributes=True)


class MovieListItemSchema(BaseModel):
    id: int
    uuid: UUID
    name: str
    year: int
    meta_score: float
    description: str

    model_config = ConfigDict(from_attributes=True)


class MovieListResponseSchema(BaseModel):
    movies: List[MovieListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int

    model_config = ConfigDict(from_attributes=True)


class MovieCreateSchema(BaseModel):
    name: str = Field(..., max_length=100)
    year: int
    time: int = Field(..., ge=0)
    imdb: float = Field(..., ge=0)
    votes: int = Field(..., ge=0)
    meta_score: float = Field(..., ge=0, le=10)
    gross: float = Field(..., ge=0)
    description: str
    price: decimal.Decimal = Field(..., ge=0)

    certification: str
    genres: List[str]
    stars: List[str]
    directors: List[str]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("certification", mode="before")
    @classmethod
    def normalize_certification(cls, value: str) -> str:
        return value.upper()

    @field_validator("genres", "stars", "directors", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: List[str]) -> List[str]:
        return [item.title() for item in value]


class MovieUpdateSchema(BaseModel):
    name: Optional[str] = None
    year: Optional[int] = None
    time: Optional[int] = Field(None, ge=0)
    imdb: Optional[float] = Field(None, ge=0)
    votes: Optional[int] = Field(None, ge=0)
    meta_score: Optional[float] = Field(None, ge=0, le=10)
    gross: Optional[int] = Field(None, ge=0)
    description: Optional[str] = None
    price: Optional[decimal.Decimal] = Field(None, ge=0)

    model_config = ConfigDict(from_attributes=True)
