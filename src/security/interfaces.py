from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Optional


class JWTAuthManagerInterface(ABC):

    @abstractmethod
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        pass

    @abstractmethod
    def create_refresh_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        pass
