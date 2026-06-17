import asyncio

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
from tasks.payments import add_movies_to_purchased_table

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post(
    "/payments/create-checkout-session",
    response_model=StripeSessionResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create Stripe Checkout Session",
    description=(
        "<h3>This endpoint initiates a Stripe Checkout payment workflow for a given pending order. "
        "It validates that the order exists, belongs to the authenticated user, and is currently in 'PENDING' status. "
        "It re-calculates and cross-checks the total order price against individual items for integrity, "
        "maps the items into Stripe format, and communicates with the Stripe API to build a Checkout Session. "
        "Finally, a local 'PENDING' payment transaction record is created in the database to log the session.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to order status mismatch, total cost discrepancy, or database constraint failures.",
            "content": {
                "application/json": {
                    "example": {"detail": "You can only pay for pending orders"}
                }
            },
        },
        404: {
            "description": "Not Found if the specified order does not exist or does not belong to the user.",
            "content": {
                "application/json": {
                    "example": {"detail": "Order not found"}
                }
            },
        },
        503: {
            "description": "Service Unavailable caused by communication failure or errors on the Stripe API gateway.",
            "content": {
                "application/json": {
                    "example": {"detail": "Payment gateway error: ..."}
                }
            },
        }
    }
)
async def create_checkout_session(
    payment_data: PaymentCreateSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Initialize a remote Stripe checkout session and log the local transaction (asynchronously).

    This function coordinates payment initiation by processing local order configurations into external
    payment data structures. It safely preloads item dependencies to audit prices, formats line items for
    Stripe, manages exceptions thrown by the gateway, and commits a persistent local tracking record inside
    the database before returning checkout links to the UI client.

    :param payment_data: Request body payload specifying the target order ID.
    :type payment_data: PaymentCreateSchema
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A schema object containing the generated Stripe checkout URL and session ID.
    :rtype: StripeSessionResponseSchema

    :raises HTTPException: Raises a 404 error if the order is missing.
    :raises HTTPException: Raises a 400 error if the order status isn't pending, prices don't audit correctly,
                           or if a local database integrity exception occurs.
    :raises HTTPException: Raises a 503 error if Stripe external communications fail.
    """
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
            cancel_url="http://127.0.0.1:8000/api/v1/payments/payments/canceled",
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
        payment_intent_id=None,
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
@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Handle Stripe Webhook Events",
    description=(
        "<h3>This public endpoint processes asynchronous event notifications sent by Stripe. "
        "It validates the integrity of the payload using the `stripe-signature` header to ensure authenticity. "
        "The handler acts upon several crucial payment lifecycle events: "
        "`checkout.session.completed` (updates payment/order status to successful/paid, creates payment items, triggers Celery tasks, and dispatches a receipt email), "
        "`checkout.session.expired` (marks the transaction as canceled due to timeout), "
        "and `charge.failed` (handles declined transactions by updating relevant records).</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to an invalid JSON payload structure or signature verification failure.",
            "content": {
                "application/json": {
                    "example": {"detail": "Signature verification failed: ..."}
                }
            },
        }
    }
)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_postgresql_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator)
):
    """
    Process asynchronous callback notifications from Stripe (asynchronously).

    This function serves as the central orchestration point for the application's payment lifecycle.
    It verifies cryptographically that incoming payloads originate from Stripe. Depending on the event state,
    it transitions database models, registers payment configurations, schedules background celery workers
    for post-payment pipelines (`add_movies_to_purchased_table`), and triggers user confirmation notifications.

    :param request: The raw FastAPI request object containing headers and byte stream payload.
    :type request: Request
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession
    :param email_sender: The email notification sender service component.
    :type email_sender: EmailSenderInterface

    :return: A JSON-compatible dictionary or status object signifying how the system handled the event.
    :rtype: dict

    :raises HTTPException: Raises a 400 error if the signature verification fails or if the payload body is malformed.
    :raises HTTPException: Raises a 400 error if a database integrity exception occurs during successful state updates.
    """
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
                return {"status": "ignored", "reason": "Payment record not found"}

            payment.payment_intent_id = session["payment_intent"]

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

            add_movies_to_purchased_table.delay(
                user_id=payment.user_id,
                order_id=payment.order_id
            )

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

    elif event["type"] == "checkout.session.expired":
        session = event["data"]["object"]

        try:
            query = (
                select(Payment)
                .where(Payment.external_payment_id == session["id"])
            )
            result = await db.execute(query)
            payment = result.scalars().first()

            if not payment:
                return {
                    "status": "error",
                    "detail": "Payment record not found for expired session"
                }

            payment.status = PaymentStatusEnum.CANCELED
            await db.commit()

            return {
                "status": "canceled",
                "message": f"Checkout session timed out. Session: {session['id']}"
            }

        except IntegrityError:
            await db.rollback()
            return {"status": "database_error"}


    elif event["type"] == "charge.failed":
        charge = event["data"]["object"]
        error_message = charge.get("failure_message")
        error_code = charge.get("failure_code")
        try:

            metadata = charge.get("metadata", {})
            order_id = metadata.get("order_id")
            if order_id:
                query = select(Payment).where(
                    Payment.order_id == int(order_id),
                    Payment.status == PaymentStatusEnum.PENDING
                )
                result = await db.execute(query)
                payment = result.scalars().first()

                if payment:
                    payment.status = PaymentStatusEnum.CANCELED
                    await db.commit()

            return {
                "status": "failed_payment_handled",
                "reason": error_message,
                "code": error_code
            }

        except IntegrityError:
            await db.rollback()
            return {"status": "database_error"}

    return {"status": "ignored"}


@router.post(
    "/orders/{order_id}/refund",
    status_code=status.HTTP_200_OK,
    summary="Refund a paid order",
    description=(
        "<h3>This endpoint processes a full refund for a previously paid order. "
        "It verifies that the order exists, belongs to the authenticated user, and has the status 'PAID'. "
        "It then locates the corresponding successful payment record to retrieve the Stripe `payment_intent_id`. "
        "The refund is issued externally via the Stripe API in a thread-safe manner, "
        "and upon success, the local payment status is updated to 'REFUNDED' and the order is marked as 'CANCELED'.</h3>"
    ),
    responses={
        400: {
            "description": "Bad Request due to Stripe API errors or gateway failures.",
            "content": {
                "application/json": {
                    "example": {"detail": "Stripe error: ..."}
                }
            },
        },
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the paid order or successful payment record does not exist for the user.",
            "content": {
                "application/json": {
                    "example": {"detail": "Order not found"}
                }
            },
        }
    }
)
async def refund_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Issue a full order refund via Stripe and reverse local transaction states (asynchronously).

    This function safely interacts with the Stripe gateway to return funds to the user. It audits
    the local order and payment eligibility criteria, offloads the synchronous external Stripe API
    call to an isolated worker thread via `asyncio.to_thread`, and executes atomic updates to roll back
    the order state to 'CANCELED' and the payment state to 'REFUNDED'.

    :param order_id: The ID of the target paid order extracted from the path URL.
    :type order_id: int
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A dictionary confirming successful refund execution alongside database identifiers.
    :rtype: dict

    :raises HTTPException: Raises a 404 error if the eligible paid order or payment record is not found.
    :raises HTTPException: Raises a 400 error if the external Stripe gateway rejects the operation.
    """
    order_query = (
        select(Order)
        .where(
            Order.id == order_id,
            Order.user_id == current_user.id,
            Order.status == OrderStatusEnum.PAID
        )
    )
    order_result = await db.execute(order_query)
    order = order_result.scalars().first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    payment_query = (
        select(Payment)
        .where(
            Payment.order_id == order_id,
            Payment.user_id == current_user.id,
            Payment.status == PaymentStatusEnum.SUCCESSFUL
        )
    )
    payment_result = await db.execute(payment_query)
    payment = payment_result.scalars().first()

    try:
        await asyncio.to_thread(
            stripe.Refund.create,
            payment_intent=payment.payment_intent_id,
        )

        payment.status = PaymentStatusEnum.REFUNDED
        order.status = OrderStatusEnum.CANCELED
        await db.commit()

    except stripe.error.StripeError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stripe error: {str(e)}"
        )

    return {"message": "Refund successful", "order_id": order.id, "status": order.status}


@router.get(
    "/payments/success",
    status_code=status.HTTP_200_OK,
    summary="Check Stripe checkout session status",
    description=(
        "<h3>This endpoint verifies the state of a local payment transaction using a Stripe Checkout session ID. "
        "It ensures that the record belongs to the currently authenticated user. "
        "Depending on the internal state (updated via asynchronous webhooks), it returns customized messaging: "
        "a thank-you notice for successful flows, a processing reminder for pending steps, "
        "or troubleshooting recommendations if the transaction has failed or been canceled.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        404: {
            "description": "Not Found if the payment record matching the provided session ID cannot be found for the user.",
            "content": {
                "application/json": {
                    "example": {"detail": "Payment not found."}
                }
            },
        }
    }
)
async def get_payments_success(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Evaluate and report the current resolution status of a payment session (asynchronously).

    This function pulls a local tracking transaction via its external session reference.
    It interprets the current model state (which is asynchronously decoupled from the gateway via Stripe Webhooks)
    and handles front-end polling by branching cleanly into semantic success, intermediate processing,
    or explicit failure responses.

    :param session_id: The Stripe checkout session token passed as a query string parameter.
    :type session_id: str
    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A dictionary payload mapping readable notifications and strict enum transaction states.
    :rtype: dict

    :raises HTTPException: Raises a 404 error if the external payment record does not exist or is mismatched.
    """
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
            "message": "Payment was declined or canceled. "
                       "Please check your card balance, ensure internet limits are sufficient, "
                       "or try a different payment method.",
            "payment_status": payment.status
        }


@router.get(
    "/payments/canceled",
    status_code=status.HTTP_200_OK,
    summary="Handle canceled Stripe checkout session redirection",
    description=(
        "<h3>This endpoint serves as the target landing page when a user explicitly cancels "
        "the payment process on the Stripe Checkout page. It provides feedback confirming "
        "the cancellation and reassures the user that their order remains intact in a pending state.</h3>"
    )
)
async def get_payments_canceled():
    """
    Handle user redirection upon canceling a payment workflow (asynchronously).

    This function responds to user actions initiated on the client side during the checkout phase.
    Since Stripe passes control back here when the cancel URL is triggered, this endpoint simply
    returns a descriptive confirmation message indicating the transaction's termination while
    affirming that the underlying order preservation state has been maintained.

    :return: A dictionary payload mapping the cancellation status and helpful user instructions.
    :rtype: dict
    """
    return {
        "status": "canceled",
        "message": "You have canceled the payment. Your order remains pending."
    }


@router.get(
    "/payments/my",
    response_model=list[PaymentResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get user payment history",
    description=(
        "<h3>This endpoint retrieves a complete list of payment transactions made by the currently authenticated user. "
        "It loads deeply nested relationships including individual payment items, associated order items, "
        "purchased movies, and their respective genres. "
        "The results are sorted chronologically, starting from the most recent payment transaction.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        }
    }
)
async def get_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Retrieve the authenticated user's payment transaction history (asynchronously).

    This function queries the database for all payment records associated with the current user.
    To prevent the N+1 problem, it optimizes data fetching by preloading nested relationships:
    payment items (`selectinload`), underlying order items (`joinedload`), purchased movies (`joinedload`),
    and movie genres (`selectinload`). The final dataset is returned sorted by creation date in descending order.

    :param current_user: The currently authenticated user object (provided via dependency injection).
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A list of payments with fully loaded items, order references, and movie metadata.
    :rtype: list[PaymentResponseSchema]
    """
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


@router.get(
    "/admin/payments",
    response_model=list[PaymentResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get all payments with advanced filtering (Admin only)",
    description=(
        "<h3>This administrative endpoint retrieves a global list of all payment transactions in the system. "
        "It supports dynamic multi-criteria filtering based on `user_id`, `start_date`, `end_date`, and `payment_status` via query parameters. "
        "To maximize performance and eliminate N+1 query bottlenecks, all nested relations including payment items, "
        "order items, movie records, and genres are eagerly fetched in a structured hierarchy. "
        "Results are returned chronologically sorted by creation date in descending order.</h3>"
    ),
    responses={
        401: {
            "description": "Unauthorized due to missing or invalid authentication token.",
        },
        403: {
            "description": "Forbidden if the authenticated user lacks administrative privileges.",
        }
    }
)
async def get_payments_for_admin(
    params: dict = Depends(admin_query_params),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_postgresql_db)
):
    """
    Retrieve and filter user payment transactions globally across the application (asynchronously).

    This function serves as an administrative logging and auditing tool. It reads optional parameters
    passed from the back-office interface, aggregates dynamic SQLAlchemy conditions, checks role-based
    permissions via the `get_admin_user` dependency, and streams pre-loaded, complex relational transaction metadata.

    :param params: A dictionary of extracted, pre-validated query parameters for multi-criteria filtering.
    :type params: dict
    :param current_user: The authenticated user object verifying administrative permissions.
    :type current_user: User
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A list of payments matching the filter criteria with full nested structural payloads.
    :rtype: list[PaymentResponseSchema]
    """
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
