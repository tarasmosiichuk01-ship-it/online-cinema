from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt


from security.interfaces import JWTAuthManagerInterface


class JWTAuthManager(JWTAuthManagerInterface):


    _ACCESS_KEY_TIMEDELTA_MINUTES = 60
    _REFRESH_KEY_TIMEDELTA_MINUTES = 60 * 24 * 7

    def __init__(self, secret_key_access: str, secret_key_refresh: str, algorithm: str):

        self._secret_key_access = secret_key_access
        self._secret_key_refresh = secret_key_refresh
        self._algorithm = algorithm

    def _create_token(self, data: dict, secret_key: str, expires_delta: timedelta) -> str:
        """
        Create a JWT token with provided data, secret key, and expiration time.
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, secret_key, algorithm=self._algorithm)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a new access token with a default or specified expiration time.
        """
        return self._create_token(
            data,
            self._secret_key_access,
            expires_delta or timedelta(minutes=self._ACCESS_KEY_TIMEDELTA_MINUTES))

    def create_refresh_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a new refresh token with a default or specified expiration time.
        """
        return self._create_token(
            data,
            self._secret_key_refresh,
            expires_delta or timedelta(minutes=self._REFRESH_KEY_TIMEDELTA_MINUTES))

