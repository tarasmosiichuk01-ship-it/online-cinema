from abc import ABC, abstractmethod


class EmailSenderInterface(ABC):

    @abstractmethod
    async def send_activation_email(self, email: str, activation_link: str) -> None:
        """
        Asynchronously send an account activation email.

        Args:
            email (str): The recipient's email address.
            activation_link (str): The activation link to include in the email.
        """
        pass

    @abstractmethod
    async def send_activation_complete_email(self, email: str, login_link: str) -> None:
        """
        Asynchronously send an email confirming that the account has been activated.

        Args:
            email (str): The recipient's email address.
            login_link (str): The login link to include in the email.
        """
        pass

    @abstractmethod
    async def send_password_reset_email(self, email: str, reset_link: str) -> None:
        """
        Asynchronously send a password reset request email.

        Args:
            email (str): The recipient's email address.
            reset_link (str): The password reset link to include in the email.
        """
        pass

    @abstractmethod
    async def send_reply_comment_email(self, email: str, comment_link: str) -> None:
        """
        Send a comment reply notification email asynchronously.

        Args:
            email (str): The recipient's email address.
            comment_link (str): The direct link to the movie comment thread.
        """
        pass

    @abstractmethod
    async def send_reaction_comment_email(self, email: str, comment_link: str) -> None:
        """
        Send a comment reaction notification email asynchronously.

        Args:
            email (str): The recipient's email address.
            comment_link (str): The direct link to the movie comment thread.
        """
        pass

    @abstractmethod
    async def send_confirmation_payment_email(
        self, email: str, order_link: str
    ) -> None:
        """
        Send a payment confirmation email asynchronously.

        Args:
            email (str): The recipient's email address.
            order_link (str): The direct link to the verified order details.
        """
        pass
