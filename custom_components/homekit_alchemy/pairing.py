"""Pairing QR code: an SVG served at a secret URL and shown in the pairing notification."""

from __future__ import annotations

import io
import secrets

from aiohttp import web
import pyqrcode

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized

from .const import DOMAIN

DATA_QR = f"{DOMAIN}_pairing_qr"  # hass.data: {notification id: (secret, svg bytes)}
QR_URL = f"/api/{DOMAIN}/pairingqr"


def qr_svg(setup_uri: str) -> bytes:
    """QR code of an X-HM:// setup URI, as SVG (scannable from the Home app)."""
    buffer = io.BytesIO()
    pyqrcode.create(setup_uri).svg(buffer, scale=5, module_color="#000", background="#FFF")
    return buffer.getvalue()


@callback
def async_publish_qr(hass: HomeAssistant, key: str, setup_uri: str) -> str:
    """Store the QR for `key` behind a fresh secret; return the image URL."""
    secret = secrets.token_hex(16)
    hass.data.setdefault(DATA_QR, {})[key] = (secret, qr_svg(setup_uri))
    return f"{QR_URL}?{key}-{secret}"


@callback
def async_forget_qr(hass: HomeAssistant, key: str) -> None:
    hass.data.get(DATA_QR, {}).pop(key, None)


class PairingQRView(HomeAssistantView):
    """Serves pairing QR codes; the random secret in the URL is the access control."""

    url = QR_URL
    name = f"api:{DOMAIN}:pairingqr"
    requires_auth = False  # <img> in a notification cannot send the auth header

    async def get(self, request: web.Request) -> web.Response:
        key, _, secret = request.query_string.rpartition("-")
        hass = request.app[KEY_HASS]
        stored = hass.data.get(DATA_QR, {}).get(key)
        if not key or not secret or stored is None or not secrets.compare_digest(stored[0], secret):
            raise Unauthorized
        return web.Response(body=stored[1], content_type="image/svg+xml")
