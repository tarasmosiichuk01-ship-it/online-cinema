import stripe
from fastapi import APIRouter, status, Depends, HTTPException, Request
from sqlalchemy import select, cast, Date
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from config.database import get_postgresql_db
from config.dependencies import get_current_user, get_accounts_email_notificator, admin_query_params, get_admin_user
from config.settings import settings
from models.accounts import User
from models.movies import Movie
from models.orders import Order, OrderStatusEnum, OrderItem
from models.payments import Payment, PaymentStatusEnum, PaymentItem
from notifications.interfaces import EmailSenderInterface
from schemas.payments import StripeSessionResponseSchema, PaymentCreateSchema, PaymentResponseSchema

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY

# Authorization endpoint
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
        .where(
            Order.id == payment_data.order_id,
            Order.user_id == current_user.id
        )
        .options(
            selectinload(Order.order_items).options(
                joinedload(OrderItem.movie).options(
                    selectinload(Movie.genres)
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

    calculated_total = sum(item.price_at_order for item in order.order_items)

    if calculated_total != order.total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order total amount mismatch with items configuration."
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
            success_url="http://127.0.0.1:8000/api/v1/payments/payments/success?session_id={CHECKOUT_SESSION_ID}",
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
        status=PaymentStatusEnum.PENDING
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


# Public endpoint
@router.post("/payments/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {e}"
        )
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signature verification failed: {e}"
        )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        try:
            query = (
                select(Payment)
                .where(Payment.external_payment_id == session["id"])
                .options(
                    joinedload(Payment.order).options(
                        selectinload(Order.order_items).options(
                            joinedload(OrderItem.movie)
                        )
                    ),
                    joinedload(Payment.user)
                )
            )
            result = await db.execute(query)
            payment = result.scalars().first()

            if not payment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Payment not found."
                )

            payment.status = PaymentStatusEnum.SUCCESSFUL
            payment.order.status = OrderStatusEnum.PAID

            for order_item in payment.order.order_items:
                payment_item = PaymentItem(
                    payment_id=payment.id,
                    order_item_id=order_item.id,
                    price_at_payment=order_item.price_at_order,
                )
                db.add(payment_item)

            await db.commit()

            order_link = f"http://127.0.0.1:8000/api/v1/orders/orders"

            await email_sender.send_confirmation_payment_email(
                email=payment.user.email,
                order_link=order_link,
            )

            return {"status": "success"}

        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database error: Could not save payment transaction."
            )

    return {"status": "ignored"}


# Authorization endpoint
@router.get("/payments/success", status_code=status.HTTP_200_OK)
async def get_payments_success(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(Payment)
        .where(
            Payment.user_id == current_user.id,
            Payment.external_payment_id == session_id,
        )
    )
    result = await db.execute(query)
    payment = result.scalars().first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found."
        )

    if payment.status == PaymentStatusEnum.SUCCESSFUL:
        return {
            "status": "success",
            "message": "Thank you for your purchase!",
            "payment_status": payment.status
        }

    elif payment.status == PaymentStatusEnum.PENDING:
        return {
            "status": "processing",
            "message": "Payment is being processed by the gateway. Please refresh in a moment.",
            "payment_status": payment.status
        }

    else:
        return {
            "status": "failed",
            "message": "Payment was not successful or was canceled.",
            "payment_status": payment.status
        }


# Authorization endpoint
@router.get(
    "/payments/my",
    response_model=list[PaymentResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    query = (
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .options(
            selectinload(Payment.payment_items).options(
                joinedload(PaymentItem.order_item).options(
                    joinedload(OrderItem.movie).options(
                        selectinload(Movie.genres)
                    )
                )
            )
        )
        .order_by(Payment.created_at.desc())
    )
    result = await db.execute(query)
    payments = result.scalars().all()

    return payments


# Admin endpoint
@router.get(
    "/admin/payments",
    response_model=list[PaymentResponseSchema],
    status_code=status.HTTP_200_OK
)
async def get_payments_for_admin(
    params: dict = Depends(admin_query_params),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    base_query = (
        select(Payment)
        .options(
            selectinload(Payment.payment_items).options(
                joinedload(PaymentItem.order_item).options(
                    joinedload(OrderItem.movie).options(
                        selectinload(Movie.genres)
                    )
                )
            )
        )
    )

    if params["user_id"] is not None:
        base_query = base_query.where(Payment.user_id == params["user_id"])

    if params["start_date"] is not None:
        base_query = base_query.where(cast(Payment.created_at, Date) >= params["start_date"])

    if params["end_date"] is not None:
        base_query = base_query.where(cast(Payment.created_at, Date) <= params["end_date"])

    if params["payment_status"] is not None:
        base_query = base_query.where(Payment.status == params["payment_status"])

    base_query = base_query.order_by(Payment.created_at.desc())

    result = await db.execute(base_query)
    payments = result.scalars().all()

    return payments
