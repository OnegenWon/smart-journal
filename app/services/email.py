"""Sending email.

With no SMTP settings, emails are printed to the server log (handy locally, and visible in your
host's log viewer). Set SMTP_HOST and friends to send real emails, for example through Gmail.
"""

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app import config


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Development sender: prints the email so you can click the link from the terminal."""

    def send(self, to: str, subject: str, body: str) -> None:
        divider = "-" * 60
        print(f"\n{divider}\nEMAIL to {to}\nSubject: {subject}\n\n{body}\n{divider}\n", flush=True)


class SmtpEmailSender:
    """Sends real email over SMTP with STARTTLS (e.g. smtp.gmail.com:587 with an app password)."""

    def __init__(self, host: str, port: int, username: str, password: str, sender: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
            smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


def get_email_sender() -> EmailSender:
    """FastAPI dependency. Tests override this to capture emails."""
    if config.SMTP_HOST:
        return SmtpEmailSender(
            host=config.SMTP_HOST,
            port=config.SMTP_PORT,
            username=config.SMTP_USERNAME,
            password=config.SMTP_PASSWORD,
            sender=config.EMAIL_FROM,
        )
    return ConsoleEmailSender()


def email_delivery_mode() -> str:
    """'email' when real emails are sent, 'log' when they're printed to the server log."""
    return "email" if config.SMTP_HOST else "log"
