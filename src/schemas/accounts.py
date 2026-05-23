from pydantic import BaseModel, EmailStr, field_validator

from validators import accounts


class BaseEmailPasswordSchema(BaseModel):
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        return accounts.validate_password_strength(value)


class UserRegistrationRequestSchema(BaseEmailPasswordSchema):
    pass


class UserRegistrationResponseSchema(BaseModel):
    id: int
    email: EmailStr

    model_config = {
        "from_attributes": True
    }


class MessageResponseSchema(BaseModel):
    message: str


class ResetActivationSchema(BaseModel):
    email: EmailStr


class UserLoginRequestSchema(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return value.lower()


class UserLoginResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserLogoutRequestSchema(BaseModel):
    refresh_token: str


class TokenRefreshRequestSchema(BaseModel):
    refresh_token: str


class TokenRefreshResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequestSchema(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password", "confirm_password")
    @classmethod
    def validate_password(cls, value):
        return accounts.validate_password_strength(value)
