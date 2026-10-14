"""Envío por WhatsApp con CallMeBot (gratis, uso personal) o Twilio."""
from __future__ import annotations

import os
import time

import requests

# Límite de Twilio por mensaje; CallMeBot admite algo más, usamos el menor.
MAX_CARACTERES = 1500


def trocear(texto: str, maximo: int = MAX_CARACTERES) -> list[str]:
    """Divide por bloques (líneas en blanco / anuncios) sin pasar del máximo."""
    trozos, actual = [], ""
    for bloque in texto.split("\n"):
        candidato = f"{actual}\n{bloque}" if actual else bloque
        if len(candidato) <= maximo:
            actual = candidato
            continue
        if actual:
            trozos.append(actual)
        while len(bloque) > maximo:
            trozos.append(bloque[:maximo])
            bloque = bloque[maximo:]
        actual = bloque
    if actual:
        trozos.append(actual)
    return trozos


def _callmebot(texto: str) -> None:
    r = requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": os.environ["WHATSAPP_TO"], "text": texto, "apikey": os.environ["CALLMEBOT_APIKEY"]},
        timeout=30,
    )
    r.raise_for_status()


def _twilio(texto: str) -> None:
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
        data={
            "From": f"whatsapp:{os.environ['TWILIO_WHATSAPP_FROM']}",
            "To": f"whatsapp:{os.environ['WHATSAPP_TO']}",
            "Body": texto,
        },
        timeout=30,
    )
    r.raise_for_status()


def enviar(texto: str, proveedor: str) -> None:
    funcion = {"callmebot": _callmebot, "twilio": _twilio}[proveedor]
    for i, trozo in enumerate(trocear(texto)):
        if i:
            time.sleep(3)  # CallMeBot rechaza mensajes muy seguidos
        funcion(trozo)
