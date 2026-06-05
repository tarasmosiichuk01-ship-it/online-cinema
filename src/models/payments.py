import enum

from src.models.base import Base

class PaymentStatusEnum(str, enum.Enum):
    SUCCESSFUL = "successful"
    CANCELED = "canceled"
    REFUNDED = "refunded"