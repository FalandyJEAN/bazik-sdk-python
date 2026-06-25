"""Async Bazik client for MonCash payments in Haiti.

Battle-tested in production (TradeMakaya). Mirrors the official Bazik API over HTTP:

    POST /token            {userID, secretKey}            -> { token, expires_at }
    POST /moncash/token    (Bearer) {gdes, referenceId…}  -> { orderId, redirectUrl, status }
    GET  /order/{orderId}  (Bearer)                        -> { status, referenceId, … }

The amount field is **gdes** (gourdes), NOT "gourdes" — sending the wrong key makes Bazik
create a payment without an amount.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from .errors import BazikError

DEFAULT_BASE_URL = "https://api.bazik.io"


class BazikClient:
    """A minimal, dependency-light (httpx only) async client for the Bazik API.

    Example
    -------
    >>> client = BazikClient(user_id="...", secret_key="...")
    >>> order = await client.create_moncash_payment(gdes=500, reference_id="INV-1",
    ...                                              webhook_url="https://api.me/webhook")
    >>> print(order["redirectUrl"])             # send the customer here to pay
    >>> result = await client.wait_for_completion(order["orderId"])
    >>> assert result["status"] == "successful"
    """

    def __init__(self, user_id: str, secret_key: str, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 20.0):
        if not user_id or not secret_key:
            raise ValueError("BazikClient requires user_id and secret_key.")
        self.user_id = user_id
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    # ---- auth -----------------------------------------------------------------
    async def authenticate(self) -> str:
        """Fetch (and cache) a bearer token. Called automatically by other methods."""
        now = time.time()
        if self._token and now < self._token_exp - 60:
            return self._token
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/token",
                                  json={"userID": self.user_id, "secretKey": self.secret_key})
        if r.status_code >= 400:
            raise BazikError(f"/token failed ({r.status_code})", r.status_code, r.text[:300])
        try:
            data = r.json()
        except Exception:
            raise BazikError("/token: non-JSON response", r.status_code, r.text[:300])
        token = data.get("token") or data.get("access_token") or (data.get("data") or {}).get("token")
        if not token:
            raise BazikError(f"/token: no token in response: {str(data)[:200]}")
        self._token = token
        exp_at = data.get("expires_at")
        self._token_exp = (exp_at / 1000) if isinstance(exp_at, (int, float)) else now + 86400
        return token

    async def _headers(self) -> dict:
        return {"Authorization": f"Bearer {await self.authenticate()}",
                "Content-Type": "application/json"}

    # ---- payments -------------------------------------------------------------
    async def create_moncash_payment(self, *, gdes: int, reference_id: str,
                                     webhook_url: Optional[str] = None,
                                     description: Optional[str] = None,
                                     customer_first_name: Optional[str] = None,
                                     customer_last_name: Optional[str] = None,
                                     customer_email: Optional[str] = None,
                                     success_url: Optional[str] = None,
                                     error_url: Optional[str] = None) -> dict[str, Any]:
        """Create a MonCash payment (max 75,000 HTG). Returns Bazik's raw response,
        including ``orderId`` and ``redirectUrl`` (where you send the customer to pay)."""
        payload: dict[str, Any] = {"gdes": gdes, "referenceId": reference_id}
        for k, v in (("description", description), ("customerFirstName", customer_first_name),
                     ("customerLastName", customer_last_name), ("customerEmail", customer_email),
                     ("webhookUrl", webhook_url), ("successUrl", success_url), ("errorUrl", error_url)):
            if v:
                payload[k] = v
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/moncash/token", json=payload,
                                  headers=await self._headers())
        if r.status_code >= 400:
            raise BazikError(f"/moncash/token failed ({r.status_code})", r.status_code, r.text[:300])
        return r.json()

    async def verify_payment(self, order_id: str) -> dict[str, Any]:
        """Fetch a payment's current status. ``status == 'successful'`` once paid
        (other values: ``'pending'``, ``'failed'``)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/order/{order_id}", headers=await self._headers())
        if r.status_code >= 400:
            raise BazikError(f"/order failed ({r.status_code})", r.status_code, r.text[:300])
        return r.json()

    async def wait_for_completion(self, order_id: str, *, interval: float = 3.0,
                                  timeout: float = 180.0) -> dict[str, Any]:
        """Poll ``verify_payment`` until the order resolves (successful/failed) or the
        timeout elapses. Returns the last status payload."""
        deadline = time.time() + timeout
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = await self.verify_payment(order_id)
            if (last.get("status") or "").lower() in ("successful", "failed", "canceled", "cancelled"):
                return last
            await asyncio.sleep(interval)
        return last
