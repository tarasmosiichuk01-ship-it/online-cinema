import stripe
from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from config.database import get_postgresql_db
from config.dependencies import get_current_user
from config.settings import settings
from models.accounts import User
from models.orders import Order, OrderStatusEnum, OrderItem
from models.payments import Payment, PaymentStatusEnum
from schemas.payments import StripeSessionResponseSchema, PaymentCreateSchema

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post(
    "/payments/create-checkout-session",
    response_model=StripeSessionResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_checkout_session(
    payment_data: PaymentCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(Order)
        .where(Order.id == payment_data.order_id, Order.user_id == current_user.id)
        .options(
            selectinload(Order.order_items).options(
                joinedload(OrderItem.movie).options(
                    joinedload(OrderItem.movie.genres)
                )
            )
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
            detail="You can only pay for pending orders"
        )

    line_items = []

    for order_item in order.order_items:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": order_item.movie.name,
                },
                "unit_amount": int(order_item.price_at_order * 100),
            },
            "quantity": 1
        })

    try:
        session = await stripe.checkout.Session.create_async(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url="http://127.0.0.1:8000/docs?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://your-site.com/cancel",
            metadata={
                "order_id": order.id,
                "user_id": current_user.id
            }
        )
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Payment gateway error: {e.user_message or str(e)}"
        )

    payment = Payment(
        user_id=current_user.id,
        order_id=order.id,
        external_payment_id=session.id,
        amount=order.total_amount,
        status=PaymentStatusEnum.CANCELED
    )

    try:
        db.add(payment)
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error: Could not save payment transaction."
        )

    return {"session_id": session.id, "checkout_url": session.url}

