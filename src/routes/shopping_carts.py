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


# Authorization endpoint
@router.post(
    "/carts",
    response_model=CartItemResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def add_movie_to_cart(
    cart_item_data: CartItemCreateSchema,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
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


# Authorization endpoint
@router.get(
    "/carts",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK
)
async def get_current_user_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
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
