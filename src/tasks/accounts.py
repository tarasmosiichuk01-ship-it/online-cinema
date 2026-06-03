import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from celery_app import celery
from config.settings import settings
from models.accounts import ActivationToken, PasswordResetToken
from models import accounts, movies, shopping_carts, orders  # noqa: F401

engine = create_engine(settings.postgres_sync_database_url, echo=False)
SyncSessionLocal = sessionmaker(engine, autocommit=False, autoflush=False)

logger = logging.getLogger(__name__)

@celery.task
def delete_expired_tokens():
    try:
        with SyncSessionLocal() as session:
            logger.info("Starting cleanup of expired tokens...")
            activation_result = session.execute(
                delete(ActivationToken)
                .where(ActivationToken.expires_at < datetime.now(timezone.utc))
            )
            reset_result = session.execute(
                delete(PasswordResetToken)
                .where(PasswordResetToken.expires_at < datetime.now(timezone.utc))
            )
            session.commit()

            logger.info(
                "Token cleanup completed. Removed %d activation tokens and %d password reset tokens.",
                activation_result.rowcount,
                reset_result.rowcount
            )
    except SQLAlchemyError as error:
        logger.error("An error occurred while deleting expired tokens: %s. Task will be retried.", error)
        raise
