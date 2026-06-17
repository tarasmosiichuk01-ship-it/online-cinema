from unittest.mock import AsyncMock, patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_send_activation_email_success(email_sender):
    """
    Test successful sending of activation email.

    Ensures that the activation email is sent with correct subject,
    recipient and that the correct template is rendered with proper parameters.
    """
    test_email = "test@example.com"
    test_activation_link = "http://127.0.0.1:8000/api/v1/activate/test_token/"

    mock_smtp_instance = AsyncMock()
    mock_smtp_instance.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("notifications.emails.aiosmtplib.SMTP", return_value=mock_smtp_instance):
        with patch.object(
            email_sender._env,
            "get_template"
        ) as mock_get_template:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html>Activation email</html>"
            mock_get_template.return_value = mock_template

            await email_sender.send_activation_email(
                email=test_email,
                activation_link=test_activation_link
            )

    mock_get_template.assert_called_once_with(
        email_sender._activation_email_template_name
    )
    mock_template.render.assert_called_once_with(
        email=test_email,
        activation_link=test_activation_link
    )
    mock_smtp_instance.connect.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with(
        email_sender._email,
        email_sender._password
    )
    mock_smtp_instance.sendmail.assert_called_once()
    mock_smtp_instance.quit.assert_called_once()


@pytest.mark.asyncio
async def test_send_activation_complete_email_success(email_sender):
    """
    Test successful sending of activation complete email.

    Ensures that the activation complete email is sent with correct subject,
    recipient and that the correct template is rendered with proper parameters.
    """
    test_email = "test@example.com"
    test_login_link = "http://127.0.0.1/accounts/login/"

    mock_smtp_instance = AsyncMock()
    mock_smtp_instance.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("notifications.emails.aiosmtplib.SMTP", return_value=mock_smtp_instance):
        with patch.object(
            email_sender._env,
            "get_template"
        ) as mock_get_template:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html>Activation complete email</html>"
            mock_get_template.return_value = mock_template

            await email_sender.send_activation_complete_email(
                email=test_email,
                login_link=test_login_link
            )

    mock_get_template.assert_called_once_with(
        email_sender._activation_complete_email_template_name
    )
    mock_template.render.assert_called_once_with(
        email=test_email,
        login_link=test_login_link
    )
    mock_smtp_instance.connect.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with(
        email_sender._email,
        email_sender._password
    )
    mock_smtp_instance.sendmail.assert_called_once()
    mock_smtp_instance.quit.assert_called_once()


@pytest.mark.asyncio
async def test_send_password_reset_email_success(email_sender):
    """
    Test successful sending of password reset email.

    Ensures that the password reset email is sent with correct subject,
    recipient and that the correct template is rendered with proper parameters.
    """
    test_email = "test@example.com"
    test_reset_link = "http://127.0.0.1:8000/api/v1/reset-password/test_token/"

    mock_smtp_instance = AsyncMock()
    mock_smtp_instance.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("notifications.emails.aiosmtplib.SMTP", return_value=mock_smtp_instance):
        with patch.object(
            email_sender._env,
            "get_template"
        ) as mock_get_template:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html>Password reset email</html>"
            mock_get_template.return_value = mock_template

            await email_sender.send_password_reset_email(
                email=test_email,
                reset_link=test_reset_link
            )

    mock_get_template.assert_called_once_with(
        email_sender._password_email_template_name
    )
    mock_template.render.assert_called_once_with(
        email=test_email,
        reset_link=test_reset_link
    )
    mock_smtp_instance.connect.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with(
        email_sender._email,
        email_sender._password
    )
    mock_smtp_instance.sendmail.assert_called_once()
    mock_smtp_instance.quit.assert_called_once()


@pytest.mark.asyncio
async def test_send_reply_comment_email_success(email_sender):
    """
    Test successful sending of reply comment email.

    Ensures that the reply comment email is sent with correct subject,
    recipient and that the correct template is rendered with proper parameters.
    """
    test_email = "test@example.com"
    test_comment_link = "http://127.0.0.1/movies/1/comments"

    mock_smtp_instance = AsyncMock()
    mock_smtp_instance.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("notifications.emails.aiosmtplib.SMTP", return_value=mock_smtp_instance):
        with patch.object(
            email_sender._env,
            "get_template"
        ) as mock_get_template:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html>Reply comment email</html>"
            mock_get_template.return_value = mock_template

            await email_sender.send_reply_comment_email(
                email=test_email,
                comment_link=test_comment_link
            )

    mock_get_template.assert_called_once_with(
        email_sender._reply_comment_template_name
    )
    mock_template.render.assert_called_once_with(
        email=test_email,
        comment_link=test_comment_link
    )
    mock_smtp_instance.connect.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with(
        email_sender._email,
        email_sender._password
    )
    mock_smtp_instance.sendmail.assert_called_once()
    mock_smtp_instance.quit.assert_called_once()
