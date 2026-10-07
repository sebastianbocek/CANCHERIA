from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from cancheria.config.settings import AppSettings

def send_text_email(subject: str, body: str) -> None:
    settings=AppSettings.from_env()
    if not (settings.email_sender and settings.email_password and settings.email_receiver):
        raise RuntimeError("Email credentials are not configured")
    msg=MIMEText(body, _charset="utf-8")
    msg["Subject"]=subject; msg["From"]=settings.email_sender; msg["To"]=settings.email_receiver
    with smtplib.SMTP_SSL("smtp.gmail.com",465) as server:
        server.login(settings.email_sender, settings.email_password)
        server.send_message(msg)
