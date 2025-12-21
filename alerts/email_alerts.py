import os
import logging
import smtplib
from email.message import EmailMessage

LOG = logging.getLogger(__name__)


def send_email(subject: str, body: str) -> bool:
    """Send an email using SMTP environment configuration.

    Required env vars (common):
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO

    If not configured, falls back to printing the message.
    Returns True if sent (or printed), False on error.
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    if not (host and user and password and email_from and email_to):
        LOG.info("SMTP not fully configured; printing email instead")
        print("[Email]", subject, body)
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.set_content(body)

    try:
        # Use STARTTLS by default for port 587
        smtp = smtplib.SMTP(host, port, timeout=10)
        smtp.ehlo()
        if port == 587:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)
        smtp.quit()
        return True
    except Exception as e:
        LOG.exception("Failed to send email: %s", e)
        return False
