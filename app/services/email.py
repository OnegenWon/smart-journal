"""Sending email. In development, emails are printed to the server terminal instead.

Swapping in a real provider (SMTP, SendGrid, Azure Communication Services) means writing
one more class with a `send` method and returning it from get_email_sender.
"""

from typing import Protocol


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Development sender: prints the email so you can click the link from the terminal."""

    def send(self, to: str, subject: str, body: str) -> None:
        divider = "-" * 60
        print(f"\n{divider}\nEMAIL to {to}\nSubject: {subject}\n\n{body}\n{divider}\n", flush=True)


def get_email_sender() -> EmailSender:
    """FastAPI dependency. Tests override this to capture emails."""
    return ConsoleEmailSender()
