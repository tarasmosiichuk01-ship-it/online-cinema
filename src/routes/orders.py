from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from config.database import get_postgresql_db
from config.dependencies import get_current_user
from models.movies import Movie
from models.orders import Order, OrderStatusEnum, OrderItem
from models.shopping_carts import Cart, CartItem
from schemas.orders import OrderResponseSchema
from models.accounts import User

router = APIRouter()


@router.post(
    "/orders",
    response_model=OrderResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_order(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    cart_query = (
        select(Cart)
        .where(Cart.user_id == current_user.id)
        .options(
            selectinload(Cart.cart_items).options(
                joinedload(CartItem.movie).options(
                    joinedload(Movie.genres)
                )
            )
        )
    )
    cart_result = await db.execute(cart_query)
    cart = cart_result.scalars().first()

    if not cart or not cart.cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your cart is empty"
        )

    new_order = Order(
        user_id=current_user.id,
        status=OrderStatusEnum.PENDING,
    )

    try:
        db.add(new_order)
        await db.flush()

        for cart_item in cart.cart_items:
            order_item = OrderItem(
                order_id=new_order.id,
                movie_id=cart_item.movie.id,
            )
            db.add(order_item)

        await db.execute(
            delete(CartItem).where(CartItem.cart_id == cart.id)
        )
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An error occurred while creating the order."
        )

    final_order_query = (
        select(Order)
        .where(Order.id == new_order.id)
        .options(
            selectinload(Order.items).options(
                joinedload(OrderItem.movie).options(
                    joinedload(Movie.genres)
                )
            )
        )
    )
    final_order_result = await db.execute(final_order_query)
    completed_order = final_order_result.scalars().first()

    return completed_order

