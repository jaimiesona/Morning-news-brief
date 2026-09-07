"""Send the brief over SMTP. Credentials come from the environment only."""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr, formatdate

from .config import config

log = logging.getLogger(__name__)


def _ssl_context() -> ssl.SSLContext:
    """TLS context with a certificate bundle that is actually present.

    A Python installed from python.org ships no CA certificates of its own, so
    smtplib cannot verify Gmail and fails with CERTIFICATE_VERIFY_FAILED. certifi
    carries a bundle, which also keeps this working on any CI runner.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        log.debug("certifi not installed; using the system certificate store")
        return ssl.create_default_context()


def build_message(subject: str, html_body: str, text_body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("Morning News Brief", config.email_from or config.smtp_user))
    message["To"] = ", ".join(config.email_to)
    message["Date"] = formatdate(localtime=True)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send(subject: str, html_body: str, text_body: str) -> bool:
    problems = config.validate_email()
    if problems:
        log.error("Cannot send email: %s", "; ".join(problems))
        return False

    message = build_message(subject, html_body, text_body)
    context = _ssl_context()
    log.info("Connecting to %s:%s", config.smtp_host, config.smtp_port)

    try:
        if config.smtp_port == 465:
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, context=context, timeout=30) as server:
                server.login(config.smtp_user, config.smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(config.smtp_user, config.smtp_password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP authentication failed. For Gmail you need an App Password, "
                  "not your normal account password.")
        return False
    except socket.gaierror as exc:
        log.error("Could not find the mail server %r: %s", config.smtp_host, exc)
        log.error("Check the SMTP_HOST setting — it should be exactly smtp.gmail.com "
                  "with no extra spaces or line breaks.")
        return False
    except ssl.SSLCertVerificationError as exc:
        log.error("Could not verify the mail server's certificate: %s", exc)
        log.error("Run: %s -m pip install --upgrade certifi", sys.executable)
        return False
    except Exception as exc:
        log.error("Failed to send email: %s", exc)
        return False

    log.info("Brief emailed to %s", ", ".join(config.email_to))
    return True
