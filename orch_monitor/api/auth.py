"""OAuth client credentials dla UiPath Automation Cloud."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

import httpx

from orch_monitor.clock import Clock, utc_now

TOKEN_URL = "https://cloud.uipath.com/identity_/connect/token"
DEFAULT_SCOPES = "OR.Robots.Read OR.Jobs.Read OR.Queues.Read OR.Folders.Read OR.Execution.Read"
REFRESH_MARGIN_S = 60


class AuthError(Exception):
    """Blad uwierzytelnienia. Komunikat nie zawiera sekretu."""

    def __init__(self, message: str, kind: Literal["credentials", "network"]) -> None:
        super().__init__(message)
        self.kind = kind


class TokenProvider:
    def __init__(
        self,
        org: str,
        client_id: str,
        client_secret: str,
        http: httpx.Client,
        scopes: str = DEFAULT_SCOPES,
        clock: Clock = utc_now,
    ) -> None:
        self._org = org
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes
        self._http = http
        self._clock = clock
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def get_token(self) -> str:
        if (
            self._token is not None
            and self._expires_at is not None
            and self._clock() < self._expires_at - timedelta(seconds=REFRESH_MARGIN_S)
        ):
            return self._token
        return self._fetch()

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = None

    def _fetch(self) -> str:
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": self._scopes,
        }
        try:
            resp = self._http.post(TOKEN_URL, data=data)
        except httpx.TimeoutException as exc:
            raise AuthError(
                "Przekroczono czas oczekiwania na serwer logowania.", "network"
            ) from exc
        except httpx.HTTPError as exc:
            raise AuthError(
                f"Blad polaczenia z serwerem logowania ({type(exc).__name__}).", "network"
            ) from exc
        if resp.status_code in (400, 401, 403):
            raise AuthError(
                f"Logowanie odrzucone (HTTP {resp.status_code}). "
                "Sprawdz client id, client secret i zakresy.",
                "credentials",
            )
        if resp.status_code != 200:
            raise AuthError(f"Serwer logowania zwrocil HTTP {resp.status_code}.", "network")
        try:
            payload = resp.json()
            token = str(payload["access_token"])
            expires_in = int(payload.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthError("Nieprawidlowa odpowiedz serwera logowania.", "credentials") from exc
        self._token = token
        self._expires_at = self._clock() + timedelta(seconds=expires_in)
        return token
