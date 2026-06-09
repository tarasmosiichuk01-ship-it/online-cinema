import decimal

from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select, delete, cast, Date, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from config.database import get_postgresql_db
from config.dependencies import get_current_user, admin_query_params, get_admin_user
from models.movies import Movie
from models.orders import Order, OrderStatusEnum, OrderItem
from models.shopping_carts import Cart, CartItem
from schemas.orders import OrderResponseSchema, OrderCreationResponseSchema
from models.accounts import User

router = APIRouter()


# Authorization endpoint
@router.post(
    "/orders",
    response_model=OrderCreationResponseSchema,
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

    cart_movie_ids = [item.movie_id for item in cart.cart_items]

    purchased_query = (
        select(OrderItem.movie_id)
        .join(Order)
        .where(
            Order.user_id == current_user.id,
            Order.status == OrderStatusEnum.PAID,
            OrderItem.movie_id.in_(cart_movie_ids)
        )
    )
    purchased_result = await db.execute(purchased_query)
    purchased_movie_ids = purchased_result.scalars().all()

    available_items = []
    warnings = []

    for cart_item in cart.cart_items:
        if cart_item.movie_id in purchased_movie_ids:
            warnings.append(f"Movie '{cart_item.movie.name}' was already purchased and was excluded.")
        elif cart_item.movie.is_available:
            available_items.append(cart_item)
        else:
            warnings.append(f"Movie '{cart_item.movie.name}' is currently unavailable and was excluded.")

    if not available_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "All movies in your cart are currently unavailable.",
                "warnings": warnings
            }
        )

    pending_check_ids = [item.movie_id for item in available_items]

    existing_pending_query = (
        select(Order.id)
        .join(OrderItem)
        .where(
            Order.user_id == current_user.id,
            Order.status == OrderStatusEnum.PENDING,
            OrderItem.movie_id.in_(pending_check_ids)
        )
        .exists()
    )
    existing_pending_result = await db.execute(select(existing_pending_query))
    existing_pending = existing_pending_result.scalar()

    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a pending order containing some of these movies. "
                   "Please complete or cancel it first."
        )

    new_order = Order(
        user_id=current_user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=sum(
            (cart_item.movie.price for cart_item in available_items),
            decimal.Decimal(0)
        )
    )

    try:
        db.add(new_order)
        await db.flush()

        for cart_item in available_items:
            order_item = OrderItem(
                order_id=new_order.id,
                movie_id=cart_item.movie.id,
                price_at_order=cart_item.movie.price,
            )
            db.add(order_item)

        await db.execute(
            delete(CartItem).where(
                CartItem.cart_id == cart.id,
                CartItem.movie_id.in_([item.movie.id for item in available_items])
            )
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
            selectinload(Order.order_items).options(
                joinedload(OrderItem.movie).options(
                    joinedload(Movie.genres)
                )
            )
        )
    )
    final_order_result = await db.execute(final_order_query)
    completed_order = final_order_result.scalars().first()

    return {"order": completed_order, "warnings": warnings}


# Authorization endpoint
@router.get(
    "/orders",
    response_model=list[OrderResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(
            selectinload(Order.order_items).options(
                joinedload(OrderItem.movie).options(
                    joinedload(Movie.genres)
                )
            )
        )
        .order_by(Order.created_at.desc())
    )
    result = await db.execute(query)
    orders = result.scalars().all()

    return orders


# Authorization endpoint
@router.patch(
    "/orders/{order_id}/cancel",
    response_model=OrderResponseSchema,
    status_code=status.HTTP_200_OK
)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    query = (
        select(Order)
        .where(
            Order.id == order_id,
            Order.user_id == current_user.id,
        )
    )
    result = await db.execute(query)
    order = result.scalars().first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only cancel pending orders"
        )

    order.status = OrderStatusEnum.CANCELED
    await db.commit()

    query_with_relations = (
        select(Order)
        .where(Order.id == order.id)
        .options(
            selectinload(Order.order_items).options(
                joinedload(OrderItem.movie).options(joinedload(Movie.genres))
            )
        )
    )
    final_result = await db.execute(query_with_relations)
    canceled_order = final_result.scalars().first()

    return canceled_order


#Admin endpoint
@router.get(
    "/admin/orders",
    response_model=list[OrderResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_order_users_by_filters(
    params: dict = Depends(admin_query_params),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_postgresql_db)
):

    base_query = (
        select(Order)
        .options(
            selectinload(Order.order_items).options(
                joinedload(OrderItem.movie).options(
                    joinedload(Movie.genres)
                )
            )
        )
    )

    if params["user_id"] is not None:
        base_query = base_query.where(Order.user_id == params["user_id"])

    if params["start_date"] is not None:
        base_query = base_query.where(cast(Order.created_at, Date) >= params["start_date"])

    if params["end_date"] is not None:
        base_query = base_query.where(cast(Order.created_at, Date) <= params["end_date"])

    if params["order_status"] is not None:
        base_query = base_query.where(Order.status == params["order_status"])

    base_query = base_query.order_by(Order.created_at.desc())

    result = await db.execute(base_query)
    orders = result.scalars().all()

    return orders
