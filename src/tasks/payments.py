import logging

from sqlalchemy import select, insert, delete, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from celery_app import celery
from config.settings import settings
from models.orders import OrderItem
from models.shopping_carts import PurchasedMovie, CartItem, Cart


engine = create_engine(settings.postgres_sync_database_url, echo=False)
SyncSessionLocal = sessionmaker(engine, autocommit=False, autoflush=False)

logger = logging.getLogger(__name__)


@celery.task
def add_movies_to_purchased_table(
    user_id: int,
    order_id: int,
):
    with SyncSessionLocal() as session:
        try:
            query = (
                select(OrderItem.movie_id)
                .where(OrderItem.order_id == order_id)
            )
            result = session.execute(query)
            movie_ids = result.scalars().all()

            if not movie_ids:
                return

            purchased_movies_data = [
                {"user_id": user_id, "movie_id": movie_id}
                for movie_id in movie_ids
            ]

            session.execute(insert(PurchasedMovie).values(purchased_movies_data))

            cart_id_subquery = select(Cart.id).where(Cart.user_id == user_id).scalar_subquery()
            session.execute(delete(CartItem).where(CartItem.cart_id == cart_id_subquery))

            session.commit()
            logger.info(f"Successfully moved {len(movie_ids)} movies to Purchased for user {user_id}")

        except SQLAlchemyError as error:
            session.rollback()
            logger.error(f"Error processing purchase for user {user_id}: {error}")
            raise error
