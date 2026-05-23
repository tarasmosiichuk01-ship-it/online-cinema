from abc import ABC, abstractmethod


class EmailSenderInterface(ABC):

    @abstractmethod
    async def send_activation_email(self, email: str, activation_link: str) -> None:
        pass

    @abstractmethod
    async def send_activation_complete_email(self, email: str, login_link: str) -> None:
        pass

    @abstractmethod
    async def send_reset_password_email(self, email: str, reset_link:str) -> None:
        pass
