"""Thin async wrapper around alexapy for shopping-list operations.

This module deliberately keeps the surface area small and well-typed so the
coordinator and config flow can be tested without touching alexapy itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from alexapy import AlexaLogin  # type: ignore[import-not-found]
from alexapy.errors import AlexapyPyotpInvalidKey  # type: ignore[import-not-found]

from .exceptions import (
    AlexaAuthError,
    AlexaAuthSelectRequired,
    AlexaCaptchaRequired,
    AlexaClaimsPickerRequired,
    AlexaConflict,
    AlexaError,
    AlexaInvalidOtpSecret,
    AlexaListNotFound,
    AlexaMfaRequired,
    MfaKind,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AlexaItem:
    """A single shopping-list item as returned by Amazon."""

    id: str
    value: str
    completed: bool
    version: int

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> AlexaItem:
        return cls(
            id=raw["id"],
            value=raw.get("value", ""),
            completed=bool(raw.get("completed", False)),
            version=int(raw.get("version", 1)),
        )


class AlexaClient:
    """Async wrapper around alexapy.AlexaLogin + the Alexa householdlists endpoints."""

    def __init__(
        self,
        url: str,
        email: str,
        password: str,
        otp_secret: str | None = None,
    ) -> None:
        self._url = url
        self._email = email
        self._password = password
        self._otp_secret = otp_secret or ""
        self._login: Any = None  # alexapy.AlexaLogin
        self._list_id: str | None = None

    # ------------------------------------------------------------------ auth

    async def login(
        self,
        *,
        securitycode: str | None = None,
        verificationcode: str | None = None,
        claimsoption: str | None = None,
        authselectoption: str | None = None,
        captcha: str | None = None,
        cookies: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log in to Amazon. Returns the persisted session state.

        Field names mirror alexapy's data keys exactly. The config flow decides
        which one to pass based on which `*_required` flag the previous attempt
        raised.

        If `otp_secret` was provided at construction time, alexapy will generate
        TOTP codes itself — the caller usually does not need to pass
        `securitycode` for authenticator-app accounts.
        """
        if self._login is None:
            try:
                self._login = AlexaLogin(
                    url=self._url,
                    email=self._email,
                    password=self._password,
                    outputpath=lambda f: f,  # we don't write cookies to disk
                    debug=False,
                    otp_secret=self._otp_secret,
                )
            except AlexapyPyotpInvalidKey as err:
                raise AlexaInvalidOtpSecret(
                    "TOTP secret is not valid base32 (allowed: A-Z, 2-7)"
                ) from err
            if cookies:
                # alexapy accepts cookies via its session jar
                self._login._cookies = cookies

        data: dict[str, str | None] = {}
        if securitycode:
            data["securitycode"] = securitycode
        if verificationcode:
            data["verificationcode"] = verificationcode
        if claimsoption:
            data["claimsoption"] = claimsoption
        if authselectoption:
            data["authselectoption"] = authselectoption
        if captcha:
            data["captcha"] = captcha

        try:
            await self._login.login(data=data)
        except Exception as err:
            _LOGGER.debug("alexapy.login raised: %s", err)
            raise AlexaAuthError(str(err)) from err

        status = dict(self._login.status or {})

        # Order matters: captcha and claimspicker can co-occur with code prompts;
        # resolve them first so the caller doesn't waste a code on the wrong page.
        if status.get("captcha_required") or status.get("verification_captcha_required"):
            raise AlexaCaptchaRequired(status.get("captcha_image_url", ""))
        if status.get("claimspicker_required"):
            raise AlexaClaimsPickerRequired(status.get("claimspicker_message", ""))
        if status.get("authselect_required"):
            raise AlexaAuthSelectRequired(status.get("authselect_message", ""))
        if status.get("securitycode_required"):
            raise AlexaMfaRequired(MfaKind.AUTHENTICATOR, status.get("message", ""))
        if status.get("verificationcode_required"):
            raise AlexaMfaRequired(MfaKind.SMS_OR_EMAIL, status.get("message", ""))
        if not status.get("login_successful"):
            raise AlexaAuthError(f"Login failed: {status}")

        return {
            "cookies": dict(self._login._cookies or {}),
            "customer_id": getattr(self._login, "customer_id", None),
            "csrf": getattr(self._login, "_csrf", None),
        }

    @property
    def is_authenticated(self) -> bool:
        return self._login is not None and bool(
            getattr(self._login, "status", {}).get("login_successful")
        )

    # ----------------------------------------------------------------- lists

    async def discover_shopping_list_id(self) -> str:
        """Find and cache the SHOPPING_LIST householdlist id."""
        if self._list_id:
            return self._list_id

        data = await self._get("/api/namedLists")
        lists = data.get("lists") or data.get("namedLists") or []
        for lst in lists:
            if lst.get("type") == "SHOPPING_LIST" or lst.get("listType") == "SHOPPING_LIST":
                self._list_id = lst.get("itemId") or lst.get("id")
                if self._list_id:
                    return self._list_id
        raise AlexaListNotFound("No SHOPPING_LIST named list found for this account")

    async def fetch_items(self) -> list[AlexaItem]:
        list_id = await self.discover_shopping_list_id()
        data = await self._get(
            f"/api/namedLists/{list_id}/items?startTime=&endTime=&listIds={list_id}"
        )
        items_raw = data.get("listItems") or data.get("items") or []
        return [AlexaItem.from_api(it) for it in items_raw]

    async def add_item(self, value: str) -> AlexaItem:
        list_id = await self.discover_shopping_list_id()
        payload = {"value": value, "listId": list_id, "completed": False}
        data = await self._post(f"/api/namedLists/{list_id}/item", payload)
        return AlexaItem.from_api(data)

    async def update_item(
        self,
        item: AlexaItem,
        *,
        value: str | None = None,
        completed: bool | None = None,
    ) -> AlexaItem:
        list_id = await self.discover_shopping_list_id()
        payload = {
            "id": item.id,
            "listId": list_id,
            "value": value if value is not None else item.value,
            "completed": completed if completed is not None else item.completed,
            "version": item.version,
        }
        try:
            data = await self._put(f"/api/namedLists/{list_id}/item/{item.id}", payload)
        except AlexaConflict:
            # Refetch to get current version, then retry once.
            current = await self._find_item(item.id)
            if current is None:
                raise
            payload["version"] = current.version
            data = await self._put(f"/api/namedLists/{list_id}/item/{item.id}", payload)
        return AlexaItem.from_api(data)

    async def delete_item(self, item: AlexaItem) -> None:
        list_id = await self.discover_shopping_list_id()
        await self._delete(f"/api/namedLists/{list_id}/item/{item.id}")

    async def _find_item(self, item_id: str) -> AlexaItem | None:
        for it in await self.fetch_items():
            if it.id == item_id:
                return it
        return None

    # --------------------------------------------------------------- transport

    def _endpoint(self, path: str) -> str:
        return f"https://alexa.{self._url}{path}"

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        if self._login is None:
            raise AlexaAuthError("Not logged in")
        session = self._login._session
        headers = dict(self._login._headers or {})
        csrf = getattr(self._login, "_csrf", None)
        if csrf:
            headers["csrf"] = csrf
        headers.setdefault("Content-Type", "application/json")

        async with session.request(
            method, self._endpoint(path), json=json, headers=headers
        ) as resp:
            if resp.status in (401, 403):
                raise AlexaAuthError(f"{method} {path} → {resp.status}")
            if resp.status == 409:
                raise AlexaConflict(f"{method} {path} → 409 version conflict")
            if resp.status >= 400:
                body = await resp.text()
                raise AlexaError(f"{method} {path} → {resp.status}: {body[:200]}")
            if resp.status == 204:
                return {}
            return await resp.json(content_type=None)

    async def _get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def _post(self, path: str, payload: dict) -> dict[str, Any]:
        return await self._request("POST", path, json=payload)

    async def _put(self, path: str, payload: dict) -> dict[str, Any]:
        return await self._request("PUT", path, json=payload)

    async def _delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)
