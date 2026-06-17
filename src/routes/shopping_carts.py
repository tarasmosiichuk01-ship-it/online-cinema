from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from config.database import get_postgresql_db
from config.dependencies import get_current_user, get_admin_user, get_optional_current_user
from models.accounts import User, UserGroupEnum
from models.movies import Movie
from models.orders import OrderItem, Order, OrderStatusEnum
from models.shopping_carts import Cart, CartItem, PurchasedMovie
from schemas.shopping_carts import CartItemCreateSchema, CartItemResponseSchema, CartResponse, PurchasedMovieResponseSchema

router = APIRouter()


@router.post(
    "/carts",
    response_model=CartItemResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Add a movie to the shopping cart",
    description=(
        "<h3>This endpoint adds a specified movie to the authenticated user's shopping cart. "
        "It enforces multiple business rules: verification of active authentication state (via optional dependency), "
        "blocking duplicate purchases of already owned movies, validating the target movie's existence, "
        "and preventing multi-instance presence of the same film in the cart. "
        "If the user does not possess an active cart instance, one is implicitly created transactionally.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to repeat purchase block, duplicate cart item inclusion, "
                           "or race-condition database integrity errors.",
            "content": {
                "application/json": {
                    "example": {"detail": "This movie is already in your cart."}
                }
            },
        },
        401: {
            "description": "Unauthorized because the request is anonymous. A redirection link to register is supplied.",
            "content": {
                "application/json": {
                    "example": {"detail": "You must sign up or log in before completing a purchase. ..."}
                }
            },
        },
        404: {
            "description": "Not Found if the requested movie identifier does not point to a valid database record.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        }
    }
)
async def add_movie_to_cart(
    cart_item_data: CartItemCreateSchema,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Append an entry to the user's active shopping cart (asynchronously).

    This function coordinates rigorous structural validations on item placement workflows.
    It catches missing session signatures early, cross-references historical order item lists to stop
    re-purchasing, hooks up lazy-initialized relational parent scopes (`Cart`), and relies on transactional
    flushes and database integrity locks to isolate clean payloads before mapping data relations outwards.

    :param cart_item_data: Request body parameters identifying the target movie to buy.
    :type cart_item_data: CartItemCreateSchema
    :param current_user: The authenticated user profile if logged in; otherwise None.
    :type current_user: User | None
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A completely loaded cart item reference wrapping linked movie descriptions and genres.
    :rtype: CartItemResponseSchema

    :raises HTTPException: Raises a 401 error if `current_user` evaluates to None.
    :raises HTTPException: Raises a 404 error if the specified movie does not exist.
    :raises HTTPException: Raises a 400 error if the user already paid for this asset,
                           the record exists in the cart, or a concurrent session raises an IntegrityError.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You must sign up or log in before completing a purchase. "
                   "Register here: http://127.0.0.1:8000/api/v1/accounts/register/"
        )

    purchased_query = select(OrderItem).join(Order).where(
        Order.user_id == current_user.id,
        Order.status == OrderStatusEnum.PAID,
        OrderItem.movie_id == cart_item_data.movie_id
    )
    purchased_result = await db.execute(purchased_query)
    existing_purchase = purchased_result.scalars().first()

    if existing_purchase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repeat purchases are not allowed."
        )

    movie_query = select(Movie).where(Movie.id == cart_item_data.movie_id)
    movie_result = await db.execute(movie_query)
    existing_movie = movie_result.scalars().first()

    if not existing_movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    cart_query = select(Cart).where(Cart.user_id == current_user.id)
    cart_result = await db.execute(cart_query)
    cart = cart_result.scalars().first()

    if not cart:
        cart = Cart(user_id=current_user.id)
        db.add(cart)
        await db.flush()

    cart_item_query = select(CartItem).where(
        CartItem.cart_id == cart.id,
        CartItem.movie_id == cart_item_data.movie_id
    )
    cart_item_result = await db.execute(cart_item_query)
    existing_cart_item = cart_item_result.scalars().first()

    if existing_cart_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This movie is already in your cart."
        )

    new_cart_item = CartItem(
        cart_id=cart.id,
        movie_id=cart_item_data.movie_id,
    )

    try:
        db.add(new_cart_item)
        await db.flush()

        completed_item_query = (
            select(CartItem)
            .where(CartItem.id == new_cart_item.id)
            .options(
                joinedload(CartItem.movie).joinedload(Movie.genres)
            )
        )
        completed_item_result = await db.execute(completed_item_query)
        completed_cart_item = completed_item_result.scalars().first()

        await db.commit()

        return completed_cart_item

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This movie is already in your cart."
        )


@router.get(
    "/carts",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user's shopping cart",
    description=(
            "<h3>This endpoint retrieves the active shopping cart for the currently authenticated user. "
            "It loads all items inside the cart along with details about the corresponding movies and their genres. "
            "If the user does not have a cart record in the database yet, the endpoint automatically returns "
            "a transient empty cart structure linked to their user ID to ensure consistent frontend rendering.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        }
    }
)
async def get_current_user_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Retrieve the authenticated user's active shopping cart (asynchronously).

    This function fetches the single cart record belonging to the user. To prevent N+1 query overhead,
    it utilizes optimized chain loading: preloading cart items via `selectinload` and deeply nesting
    the related movies and genres using sequential `joinedload` expressions. If no cart instance exists,
    an unpersisted empty model placeholder is returned as a fallback.

    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A database-backed or dynamically generated Cart model with eager-loaded collections.
    :rtype: CartResponse
    """
    query = (
        select(Cart)
        .where(Cart.user_id == current_user.id)
        .options(
            selectinload(Cart.cart_items)
            .joinedload(CartItem.movie)
            .joinedload(Movie.genres)
        )
    )
    result = await db.execute(query)
    cart = result.scalars().first()

    if not cart:
        return Cart(user_id=current_user.id, cart_items=[])

    return cart


# Authorization endpoint
@router.delete("/carts/items/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cart_item(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(CartItem)
        .join(Cart)
        .where(
            CartItem.movie_id == movie_id,
            Cart.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    cart_item = result.scalars().first()

    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This movie is not in your cart."
        )

    await db.delete(cart_item)
    await db.commit()


# Authorization endpoint
@router.delete("/carts/clear", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cart_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    delete_query = (
        delete(CartItem)
        .where(
            CartItem.cart_id == (
                select(Cart.id).where(Cart.user_id == current_user.id).scalar_subquery()
            )
        )
    )
    await db.execute(delete_query)
    await db.commit()


# Admin endpoint
@router.get(
    "/admin/carts/{user_id}",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK
)
async def get_cart_by_user_id(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(Cart)
        .where(Cart.user_id == user_id)
        .options(
            selectinload(Cart.cart_items)
            .joinedload(CartItem.movie)
            .joinedload(Movie.genres)
        )
    )
    result = await db.execute(query)
    cart = result.scalars().first()

    if not cart:
        return Cart(user_id=user_id, cart_items=[])

    return cart


# Authorization endpoint
@router.get(
    "/carts/purchased",
    response_model=list[PurchasedMovieResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_purchased_movies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(PurchasedMovie)
        .where(PurchasedMovie.user_id == current_user.id)
        .options(
            selectinload(PurchasedMovie.movie)
            .selectinload(Movie.genres)
        )
    )
    result = await db.execute(query)
    purchased_movies = result.scalars().all()

    return purchased_movies
