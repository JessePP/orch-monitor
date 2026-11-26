"""Klient OData Orchestratora (tylko odczyt)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from orch_monitor.api.auth import TokenProvider

MAX_RETRIES = 3
BASE_BACKOFF_S = 1.0


OnRequest = Callable[[str, str, int, float], None]


class ApiError(Exception):
    """Blad API po wyczerpaniu ponowien. status 0 = blad sieci."""

    def __init__(self, status: int, path: str, message: str = "") -> None:
        super().__init__(message or f"Blad API Orchestratora: HTTP {status} dla {path}")
        self.status = status
        self.path = path


class OrchestratorClient:
    def __init__(
        self,
        org: str,
        tenant: str,
        token_provider: TokenProvider,
        http: httpx.Client,
        sleep: Callable[[float], None] = time.sleep,
        on_request: OnRequest | None = None,
    ) -> None:
        self._base = f"https://cloud.uipath.com/{org}/{tenant}/orchestrator_/odata/"
        self._tokens = token_provider
        self._http = http
        self._sleep = sleep
        self._on_request = on_request

    @property
    def base_url(self) -> str:
        return self._base

    def _url(self, path: str, params: Mapping[str, Any] | None) -> str:
        url = self._base + path.lstrip("/")
        if params:
            url += "?" + urlencode(params, quote_via=quote, safe="$")
        return url

    def _headers(self, folder_id: int | None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._tokens.get_token()}",
            "Accept": "application/json",
        }
        if folder_id is not None:
            headers["X-UIPATH-OrganizationUnitId"] = str(folder_id)
        return headers

    @staticmethod
    def _retry_delay(resp: httpx.Response | None, attempt: int) -> float:
        if resp is not None:
            raw = resp.headers.get("Retry-After")
            if raw is not None:
                try:
                    return max(0.0, float(raw))
                except ValueError:
                    pass
        return float(BASE_BACKOFF_S * (2**attempt))

    def _request(self, url: str, path: str, folder_id: int | None) -> httpx.Response:
        retries = 0
        reauthed = False
        while True:
            headers = self._headers(folder_id)
            started = time.perf_counter()
            resp: httpx.Response | None = None
            try:
                resp = self._http.get(url, headers=headers)
                status = resp.status_code
            except httpx.HTTPError:
                status = 0
            if self._on_request is not None:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                self._on_request("GET", path, status, elapsed_ms)
            if status == 401 and not reauthed:
                reauthed = True
                self._tokens.invalidate()
                continue
            if status == 0 or status == 429 or status >= 500:
                if retries >= MAX_RETRIES:
                    raise ApiError(status, path)
                self._sleep(self._retry_delay(resp, retries))
                retries += 1
                continue
            if status >= 400:
                raise ApiError(status, path)
            assert resp is not None
            return resp

    def get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        resp = self._request(self._url(path, params), path, folder_id)
        data = resp.json()
        if not isinstance(data, dict):
            raise ApiError(resp.status_code, path, f"Nieoczekiwana odpowiedz dla {path}")
        return data

    def get_all(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        folder_id: int | None = None,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        skip = 0
        url: str | None = self._url(path, {**(params or {}), "$top": page_size, "$skip": 0})
        while url is not None:
            resp = self._request(url, path, folder_id)
            data = resp.json()
            page = data.get("value", []) if isinstance(data, dict) else []
            items.extend(page)
            next_link = data.get("@odata.nextLink") if isinstance(data, dict) else None
            skip += len(page)
            if next_link:
                url = str(next_link)
            elif len(page) >= page_size:
                url = self._url(path, {**(params or {}), "$top": page_size, "$skip": skip})
            else:
                url = None
        return items

    def count(
        self,
        path: str,
        filter: str | None = None,  # noqa: A002
        folder_id: int | None = None,
    ) -> int:
        params = {"$filter": filter} if filter else None
        count_path = path.rstrip("/") + "/$count"
        resp = self._request(self._url(count_path, params), count_path, folder_id)
        try:
            return int(resp.text.strip())
        except ValueError as exc:
            raise ApiError(resp.status_code, count_path, "Nieprawidlowa odpowiedz $count") from exc
