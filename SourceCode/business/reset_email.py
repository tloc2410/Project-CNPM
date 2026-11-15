"""Simple SMTP sender. Never write an app password or reset link to GitHub/logs."""
import os
import smtplib
import ssl
from email.message import EmailMessage


def send_reset_email(recipient, reset_url):
    host = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    sender = os.environ.get("MAIL_FROM") or username
    if not username or not password or not sender:
        raise RuntimeError("SMTP not configured: MAIL_USERNAME, MAIL_PASSWORD and MAIL_FROM")

    msg = EmailMessage()
    msg["Subject"] = "Reset your Group12 Car Rental password"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "We received a request to reset your password.\n\n"
        f"Open this link within 15 minutes:\n{reset_url}\n\n"
        "If you did not request this, ignore this email.\n"
    )
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(msg)
