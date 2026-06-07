import math

from fastapi import APIRouter, status, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, asc, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from config.dependencies import get_moderator_user, get_query_params
from config.database import get_postgresql_db
from models.accounts import User
from models.movies import Movie, Genre, Star, Director
from models.orders import OrderStatusEnum, OrderItem, Order
from models.shopping_carts import CartItem
from schemas.movies import (
    MovieDetailSchema,
    MovieCreateSchema,
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieUpdateSchema
)
from utils.utils import resolve_movie_relations

router = APIRouter()

# Moderators endpoint
@router.post(
    "/movies",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_movie(
    movie_data: MovieCreateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    existing_query = select(Movie).where(
        (Movie.name == movie_data.name),
        (Movie.year == movie_data.year),
        (Movie.time == movie_data.time)
    )
    existing_result = await db.execute(existing_query)
    existing_movie = existing_result.scalars().first()

    if existing_movie:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A movie with the name '{movie_data.name}' and release year "
                f"'{movie_data.year}' already exists."
            )
        )

    genres, stars, directors, certification = await resolve_movie_relations(
        db=db,
        genres=movie_data.genres,
        stars=movie_data.stars,
        directors=movie_data.directors,
        certification=movie_data.certification,
    )

    try:
        new_movie = Movie(
            name=movie_data.name,
            year=movie_data.year,
            time=movie_data.time,
            imdb=movie_data.imdb,
            votes=movie_data.votes,
            meta_score=movie_data.meta_score,
            gross=movie_data.gross,
            description=movie_data.description,
            price=movie_data.price,
            certification=certification,
            genres=genres,
            stars=stars,
            directors=directors
        )

        db.add(new_movie)
        await db.commit()
        await db.refresh(new_movie, ["certification", "genres", "stars", "directors"])

        return MovieDetailSchema.model_validate(new_movie)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")



# Public endpoint
@router.get(
    "/movies",
    response_model=MovieListResponseSchema
)
async def get_movie_list(
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    params: dict = Depends(get_query_params),
    db: AsyncSession = Depends(get_postgresql_db)
) -> MovieListResponseSchema:

    base_query = select(Movie).where(Movie.is_available == True)
    count_query = select(func.count()).select_from(Movie).where(Movie.is_available == True)

    if params["release_year"]:
        base_query = base_query.where(Movie.year == params["release_year"])
        count_query = count_query.where(Movie.year == params["release_year"])

    if params["min_rating_imdb"]:
        base_query = base_query.where(Movie.imdb >= params["min_rating_imdb"])
        count_query = count_query.where(Movie.imdb >= params["min_rating_imdb"])

    if params["genre"]:
        genre_condition = Movie.genres.any(Genre.name.ilike(f"%{params['genre']}%"))
        base_query = base_query.where(genre_condition)
        count_query = count_query.where(genre_condition)

    if params["search"]:
        search_term = f"%{params['search']}%"

        movie_text_condition = (Movie.name.ilike(search_term)) | (Movie.description.ilike(search_term))
        star_condition = Movie.stars.any(Star.name.ilike(search_term))
        director_condition = Movie.directors.any(Director.name.ilike(search_term))

        full_search_condition = movie_text_condition | star_condition | director_condition

        base_query = base_query.where(full_search_condition)
        count_query = count_query.where(full_search_condition)

    sort_mapping = {
        "id": Movie.id,
        "year": Movie.year,
        "price": Movie.price,
        "votes": Movie.votes,
    }
    sort_column = sort_mapping.get(params["sort_by"], Movie.id)

    if params["order"] == "asc":
        base_query = base_query.order_by(asc(sort_column))
    else:
        base_query = base_query.order_by(desc(sort_column))

    total_items_result = await db.execute(count_query)
    total_items = total_items_result.scalar() or 0

    total_pages = 1 if total_items == 0 else math.ceil(total_items / per_page)
    prev_page = f"/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"/movies/?page={page + 1}&per_page={per_page}" if page < total_pages else None

    queryset = (
        base_query
        .options(joinedload(Movie.certification), selectinload(Movie.genres))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(queryset)
    movies = result.scalars().all()

    if not movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No movies found.")

    movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]

    return MovieListResponseSchema(
        movies=movie_list,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


# Public endpoint
@router.get(
    "/movies/{movie_id}",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_200_OK
)
async def get_movie_by_id(movie_id: int, db: AsyncSession = Depends(get_postgresql_db)):
    query = (
        select(Movie)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
        )
        .where(Movie.id == movie_id, Movie.is_available == True)
    )
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    return MovieDetailSchema.model_validate(movie)


# Moderators endpoint
@router.patch(
    "/movies/{movie_id}",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_200_OK
)
async def update_movie(
    movie_id: int,
    movie_data: MovieUpdateSchema,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(Movie)
        .options(
            joinedload(Movie.certification),
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
        )
        .where(Movie.id == movie_id)
    )
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    update_dict = movie_data.model_dump(exclude_unset=True)

    genres, stars, directors, certification = await resolve_movie_relations(
        db=db,
        genres=update_dict.get("genres"),
        stars=update_dict.get("stars"),
        directors=update_dict.get("directors"),
        certification=update_dict.get("certification")
    )

    if genres is not None: movie.genres = genres
    if stars is not None: movie.stars = stars
    if directors is not None: movie.directors = directors
    if certification is not None: movie.certification = certification

    movie_fields = {"genres", "stars", "directors", "certification"}
    for field, value in update_dict.items():
        if field not in movie_fields:
            setattr(movie, field, value)

    try:
        await db.commit()
        await db.refresh(movie, ["certification", "genres", "stars", "directors"])
        return MovieDetailSchema.model_validate(movie)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data.")



# Moderators endpoint
@router.delete("/movies/{movie_id}", status_code=status.HTTP_200_OK)
async def delete_movie(
    movie_id: int,
    current_user: User = Depends(get_moderator_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    query = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(query)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    cart_check_query = select(CartItem).where(CartItem.movie_id == movie_id)
    cart_check_result = await db.execute(cart_check_query)
    existing_in_cart = cart_check_result.scalars().first()

    if existing_in_cart:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Warning to Moderator: This movie cannot be deleted because it is currently in users' shopping carts."
        )

    query_purchased = (
        select(exists())
        .where(OrderItem.movie_id == movie_id)
        .join(Order)
        .where(Order.status == OrderStatusEnum.PAID)
    )
    result_purchased = await db.execute(query_purchased)
    has_been_purchased = result_purchased.scalar()

    if has_been_purchased:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This movie cannot be deleted because it has already been purchased by at least one user."
        )

    await db.delete(movie)
    await db.commit()

    return {"detail": "Movie deleted successfully."}
