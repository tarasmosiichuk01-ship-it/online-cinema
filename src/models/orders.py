import decimal
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, DateTime, func, Enum, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class StatusEnum(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"



