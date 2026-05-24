from celery import Celery
from celery.schedules import crontab

from config.settings import settings

celery = Celery(
    "online_cinema",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks.accounts"]
)

celery.conf.beat_schedule = {
    "delete-expired-tokens": {
        "task": "tasks.accounts.delete_expired_tokens",
        "schedule": crontab(hour="*/1"),
    }
}
