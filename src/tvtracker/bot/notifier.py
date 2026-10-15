"""Synchronous Telegram sender used by the daily job."""

from __future__ import annotations

import httpx


class TelegramSendError(Exception):
    """Telegram did not accept the notification."""


class TelegramNotifier:
    def __init__(self, token: str, *, client: httpx.Client | None = None) -> None:
        self._token = token
        self._client = client or httpx.Client(timeout=30.0)

    def send(self, chat_id: int, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            response = self._client.post(url, json={"chat_id": chat_id, "text": text})
        except httpx.HTTPError:
            raise TelegramSendError("Telegram request failed") from None
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramSendError("Telegram returned invalid JSON") from exc
        if response.status_code >= 400 or not isinstance(payload, dict) or not payload.get("ok"):
            raise TelegramSendError(f"Telegram returned HTTP {response.status_code}")
