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


@router.post(
    "/orders",
    response_model=OrderCreationResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new pending order from the cart",
    description=(
        "<h3>This endpoint processes the user's shopping cart to generate a new order. "
        "It automatically filters out movies that have already been purchased and movies "
        "that are currently unavailable, returning appropriate warnings. "
        "It ensures that no duplicate pending orders exist for the same movies, "
        "calculates the total price, moves the valid items to a new order with 'PENDING' status, "
        "and clears those items from the user's cart transactionally.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to empty cart, all filtered items being unavailable, "
                           "or an existing pending order with the same movies.",
            "content": {
                "application/json": {
                    "example": {"detail": "Your cart is empty"}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        }
    }
)
async def create_order(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Checkout the current user's cart and generate a pending order (asynchronously).

    This function performs a series of business logic checks before order placement:
    1. Fetches the user's cart and items.
    2. Filters out previously bought or deactivated movies.
    3. Blocks the creation if there's already an unfulfilled pending order for the same items.
    4. Transactionally builds the order structure, computes totals, and flushes the handled items from the cart.

    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A schema object containing the newly created order record along with system execution warnings.
    :rtype: OrderCreationResponseSchema

    :raises HTTPException: Raises a 400 error if the cart is empty, all selected movies are restricted,
                           a duplicate pending workflow is detected, or an IntegrityError occurs.
    """
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


@router.get(
    "/orders",
    response_model=list[OrderResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get user order history",
    description=(
        "<h3>This endpoint retrieves a complete list of orders placed by the currently authenticated user. "
        "It fetches all order items, including details about the ordered movies and their genres. "
        "The results are ordered chronologically, starting from the most recent order.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        }
    }
)
async def get_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Retrieve the authenticated user's order history (asynchronously).

    This function queries the database for all orders belonging to the current user.
    To avoid the N+1 problem, it optimizes data fetching by preloading nested relationships:
    order items (`selectinload`), associated movies (`joinedload`), and their respective genres (`joinedload`).
    The final list is sorted by creation date in descending order.

    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A list of orders containing items, movie profiles, and genres metadata.
    :rtype: list[OrderResponseSchema]
    """
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


@router.patch(
    "/orders/{order_id}/cancel",
    response_model=OrderResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending order",
    description=(
        "<h3>This endpoint allows a user to cancel an existing order. "
        "It verifies that the order belongs to the authenticated user and checks its status. "
        "An order can only be canceled if its current status is 'PENDING'. "
        "Once validated, the status is updated to 'CANCELED', and the order details, "
        "including items and movie relationships, are loaded and returned.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request because the order status is not PENDING.",
            "content": {
                "application/json": {
                    "example": {"detail": "You can only cancel pending orders"}
                }
            },
        },
        404: {
            "description": "Not Found if the order does not exist or does not belong to the user.",
            "content": {
                "application/json": {
                    "example": {"detail": "Order not found"}
                }
            },
        }
    }
)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Cancel an active pending order (asynchronously).

    This function safely modifies the state of an order. It performs a database lookup by
    order ID and user ID, applies strict business validation rules regarding state transitions,
    and transactionally transitions the order status to 'CANCELED'. Finally, it refreshes
    and preloads nested movie and genre records to satisfy the response schema.

    :param order_id: The ID of the target order extracted from the path URL.
    :type order_id: int
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: The updated order object with loaded nested relationships.
    :rtype: OrderResponseSchema

    :raises HTTPException: Raises a 404 error if the order is missing or unauthorized.
    :raises HTTPException: Raises a 400 error if the order is already processed, paid, or canceled.
    """
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


@router.get(
    "/admin/orders",
    response_model=list[OrderResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get all orders with advanced filtering (Admin only)",
    description=(
        "<h3>This administrative endpoint retrieves a list of all user orders from the database. "
        "It supports dynamic filtering based on `user_id`, `start_date`, "
        "`end_date`, and `order_status` via query parameters. "
        "To prevent the N+1 problem, all related data including order items, "
        "movie details, and genres are eagerly loaded. "
        "The list is sorted chronologically by creation date in descending order.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        403: {
            "description": "Forbidden if the authenticated user does not have administrative privileges.",
        }
    }
)
async def get_order_users_by_filters(
    params: dict = Depends(admin_query_params),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Retrieve and filter user orders globally across the application (asynchronously).

    This function acts as a back-office management tool. It constructs a dynamic SQLAlchemy query
    by inspecting the optional criteria passed through administrative query parameters.
    It ensures strict separation of concerns by applying a role-based dependency (`get_admin_user`)
    and optimizes database performance through deeply nested relation preloading.

    :param params: A dictionary of extracted, pre-validated query parameters for multi-criteria filtering.
    :type params: dict
    :param current_user: The authenticated user object verifying administrative permissions.
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A list of orders matching the specified filter criteria with full nested payloads.
    :rtype: list[OrderResponseSchema]
    """
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
