from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def enviar(asunto: str, html: str, texto: str) -> None:
    """Envía por SMTP. Con Gmail: SMTP_HOST=smtp.gmail.com y una 'contraseña de aplicación'."""
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    puerto = int(os.environ.get("SMTP_PORT") or "465")
    usuario = os.environ["SMTP_USER"]
    destino = os.environ.get("EMAIL_TO") or usuario

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = os.environ.get("EMAIL_FROM") or usuario
    msg["To"] = destino
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    if puerto == 465:
        with smtplib.SMTP_SSL(host, puerto, timeout=30) as s:
            s.login(usuario, os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, puerto, timeout=30) as s:
            s.starttls()
            s.login(usuario, os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
