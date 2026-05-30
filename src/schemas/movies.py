import decimal
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict

from models.movies import ReactionTypeEnum


class GenreBaseSchema(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)


class GenreDetailSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class GenreCreateShema(GenreBaseSchema):
    pass


class GenreUpdateShema(GenreBaseSchema):
    name: Optional[str] = None


class GenreListResponseSchema(BaseModel):
    genres: List[GenreDetailSchema]

    model_config = ConfigDict(from_attributes=True)


class GenreWithMoviesCountSchema(BaseModel):
    id: int
    name: str
    movies_count: int


class StarBaseSchema(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)


class StarCreateSchema(StarBaseSchema):
    pass


class StarUpdateSchema(StarBaseSchema):
    name: Optional[str] = None


class StarResponseSchema(StarBaseSchema):
    id: int


class StarListResponseSchema(BaseModel):
    stars: List[StarResponseSchema]

    model_config = ConfigDict(from_attributes=True)


class DirectorBaseSchema(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)


class DirectorCreateSchema(DirectorBaseSchema):
    pass


class DirectorUpdateSchema(DirectorBaseSchema):
    name: Optional[str] = None


class DirectorResponseSchema(DirectorBaseSchema):
    id: int


class DirectorListResponseSchema(BaseModel):
    directors: List[DirectorResponseSchema]

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
    meta_score: Optional[float] = Field(None, ge=0, le=100)
    gross: Optional[float] = Field(None, ge=0)
    description: str
    price: decimal.Decimal = Field(..., ge=0)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("year")
    @classmethod
    def validate_year(cls, value):
        current_year = datetime.now().year
        if value > current_year + 1:
            raise ValueError(f"The year in 'year' cannot be greater than {current_year + 1}.")
        return value


class MovieDetailSchema(MovieBaseSchema):
    id: int
    uuid: UUID
    certification: CertificationSchema
    genres: List[GenreDetailSchema]
    stars: List[StarBaseSchema]
    directors: List[DirectorBaseSchema]

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


class MovieCreateSchema(MovieBaseSchema):
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


class MovieCommentBaseSchema(BaseModel):
    text: str

    model_config = ConfigDict(from_attributes=True)


class MovieCommentCreateSchema(MovieCommentBaseSchema):
    parent_id: Optional[int] = None


class MovieCommentUpdateSchema(MovieCommentBaseSchema):
    pass


class MovieCommentResponseSchema(BaseModel):
    id: int
    user: str
    text: str
    created_at: datetime
    replies: List["MovieCommentResponseSchema"] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("user", mode="before")
    @classmethod
    def convert_user_to_string(cls, value):
        if hasattr(value, "email"):
            return value.email
        return value


class CommentReactionCreate(BaseModel):
    reaction_type: ReactionTypeEnum

class CommentReactionResponse(BaseModel):
    id: int
    comment_id: int
    user_id: int
    reaction_type: ReactionTypeEnum
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MovieReactionCreateSchema(BaseModel):
    reaction_type: ReactionTypeEnum


class MovieReactionResponseSchema(BaseModel):
    id: int
    reaction_type: ReactionTypeEnum
    movie_id: int


class MovieRatingSchema(BaseModel):
    rating: int = Field(..., ge=1, le=10)


class MovieRatingResponseSchema(BaseModel):
    id: int
    rating: int
    movie_id: int

class MovieFavouriteSchema(BaseModel):
    movie_id: int

class MovieFavouriteResponseSchema(BaseModel):
    id: int
    movie: MovieListItemSchema
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
