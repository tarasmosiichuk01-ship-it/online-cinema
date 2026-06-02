from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.database import get_postgresql_db
from config.dependencies import get_current_user
from models.accounts import User, UserGroupEnum
from models.movies import Movie
from models.shopping_carts import Cart, CartItem
from schemas.shopping_carts import CartItemCreateSchema, CartItemResponseSchema

router = APIRouter()


# Authorization endpoint
@router.post(
    "/carts",
    response_model=CartItemResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def add_movie_to_cart(
    cart_item_data: CartItemCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    if not current_user.has_group(UserGroupEnum.USER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to perform this action. "
                   "Please register here http://127.0.0.1:8000/api/v1/accounts/register/"
        )

    #purchased_query = select(OrderItem).join(Order).where(
    #    Order.user_id == current_user.id,
    #    Order.status == OrderStatusEnum.PAID,
    #    OrderItem.movie_id == cart_item_data.movie_id
    #)
    #purchased_result = await db.execute(purchased_query)
    #existing_purchase = purchased_result.scalars().first()
    #
    #if existing_purchase:
    #    raise HTTPException(
    #        status_code=status.HTTP_400_BAD_REQUEST,
    #        detail="Repeat purchases are not allowed."
    #    )

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
        await db.commit()

        completed_item_query = (
            select(CartItem)
            .where(CartItem.id == new_cart_item.id)
            .options(
                joinedload(CartItem.movie).joinedload(Movie.genres)
            )
        )
        completed_item_result = await db.execute(completed_item_query)
        completed_cart_item = completed_item_result.scalars().first()

        return completed_cart_item

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This movie is already in your cart."
        )