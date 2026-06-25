"""Async Bazik client — MonCash & NatCash payments, payouts, transfers and wallet for Haiti.

Production-tested (powers payments on TradeMakaya). One dependency: ``httpx``.

Base URL: ``https://api.bazik.io``

    POST /token                        {userID, secretKey}            -> { token, expires_at }
    POST /moncash/token                {gdes, referenceId, …}         -> { orderId, redirectUrl, status }
    GET  /order/{orderId}                                             -> { status, referenceId, … }
    POST /moncash/withdraw             {gdes, wallet, …}              -> { … }            (payout)
    GET  /balance                                                    -> { available, reserved }
    POST /moncash/customers/status     {wallet}                       -> { … }            (KYC)
    POST /moncash/transfers            {gdes, wallet, …}              -> { transactionId }
    POST /natcash/transfers            {gdes, wallet, …}              -> { transactionId }
    GET  /transfers/{id}                                             -> { status, … }
    POST /transfers/quote              {gdes, provider}               -> { fee, … }
    GET  /wallet                                                     -> { balance }

The amount field is **gdes** (gourdes), NOT "gourdes".
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from .errors import BazikError

DEFAULT_BASE_URL = "https://api.bazik.io"

# Order / transfer status values returned by Bazik.
STATUS_PENDING = "pending"
STATUS_SUCCESSFUL = "successful"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
_TERMINAL = {STATUS_SUCCESSFUL, STATUS_FAILED, STATUS_CANCELLED, "canceled", "processing_failed"}


class BazikClient:
    """Async client for the Bazik API.

    Use as an async context manager to reuse one HTTP connection pool::

        async with BazikClient(user_id="…", secret_key="…") as bazik:
            order = await bazik.create_moncash_payment(gdes=500, reference_id="INV-1")
            print(order["redirectUrl"])

    or standalone (a client is created lazily; call ``await aclose()`` when done).
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
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BazikClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._http

    # ---- auth -----------------------------------------------------------------
    async def authenticate(self) -> str:
        """Fetch & cache a bearer token (24h). Called automatically by other methods."""
        now = time.time()
        if self._token and now < self._token_exp - 60:
            return self._token
        r = await self._client().post("/token", json={"userID": self.user_id, "secretKey": self.secret_key})
        data = self._json(r, "/token")
        token = data.get("token") or data.get("access_token") or (data.get("data") or {}).get("token")
        if not token:
            raise BazikError(f"/token: no token in response: {str(data)[:200]}")
        self._token = token
        exp_at = data.get("expires_at")
        self._token_exp = (exp_at / 1000) if isinstance(exp_at, (int, float)) else now + 86400
        return token

    # ---- low-level helpers ----------------------------------------------------
    @staticmethod
    def _json(r: httpx.Response, what: str) -> dict[str, Any]:
        if r.status_code >= 400:
            raise BazikError(f"{what} failed ({r.status_code})", r.status_code, r.text[:300])
        try:
            return r.json()
        except Exception:
            raise BazikError(f"{what}: non-JSON response", r.status_code, r.text[:300])

    async def _get(self, path: str) -> dict[str, Any]:
        token = await self.authenticate()
        r = await self._client().get(path, headers={"Authorization": f"Bearer {token}"})
        return self._json(r, path)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        token = await self.authenticate()
        r = await self._client().post(path, json={k: v for k, v in body.items() if v is not None},
                                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        return self._json(r, path)

    # ---- payments -------------------------------------------------------------
    async def create_moncash_payment(self, *, gdes: int, reference_id: str,
                                     webhook_url: Optional[str] = None,
                                     description: Optional[str] = None,
                                     customer_first_name: Optional[str] = None,
                                     customer_last_name: Optional[str] = None,
                                     customer_email: Optional[str] = None,
                                     success_url: Optional[str] = None,
                                     error_url: Optional[str] = None) -> dict[str, Any]:
        """Create a MonCash payment (max 75,000 HTG). Returns ``{orderId, redirectUrl, …}``
        — send the customer to ``redirectUrl`` to pay."""
        return await self._post("/moncash/token", {
            "gdes": gdes, "referenceId": reference_id, "description": description,
            "customerFirstName": customer_first_name, "customerLastName": customer_last_name,
            "customerEmail": customer_email, "webhookUrl": webhook_url,
            "successUrl": success_url, "errorUrl": error_url,
        })

    async def verify_payment(self, order_id: str) -> dict[str, Any]:
        """Fetch a payment's status. ``status == 'successful'`` once paid."""
        return await self._get(f"/order/{order_id}")

    async def is_paid(self, order_id: str) -> bool:
        """Convenience: True if the order's status is 'successful'."""
        return (await self.verify_payment(order_id)).get("status") == STATUS_SUCCESSFUL

    async def wait_for_completion(self, order_id: str, *, interval: float = 3.0,
                                  timeout: float = 180.0) -> dict[str, Any]:
        """Poll ``verify_payment`` until the order resolves or the timeout elapses."""
        deadline = time.time() + timeout
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = await self.verify_payment(order_id)
            if (last.get("status") or "").lower() in _TERMINAL:
                return last
            await asyncio.sleep(interval)
        return last

    async def withdraw(self, *, gdes: int, wallet: str,
                       description: Optional[str] = None) -> dict[str, Any]:
        """Pay out from your Bazik account to a MonCash wallet."""
        return await self._post("/moncash/withdraw", {"gdes": gdes, "wallet": wallet, "description": description})

    async def get_balance(self) -> dict[str, Any]:
        """Account balance: ``{available, reserved}``."""
        return await self._get("/balance")

    # ---- transfers ------------------------------------------------------------
    async def check_customer(self, wallet: str) -> dict[str, Any]:
        """Validate a MonCash wallet's KYC status before sending money."""
        return await self._post("/moncash/customers/status", {"wallet": wallet})

    async def transfer_moncash(self, *, gdes: int, wallet: str,
                               customer_first_name: Optional[str] = None,
                               customer_last_name: Optional[str] = None,
                               description: Optional[str] = None) -> dict[str, Any]:
        """Send a MonCash transfer. Returns ``{transactionId, …}``."""
        return await self._post("/moncash/transfers", {
            "gdes": gdes, "wallet": wallet, "customerFirstName": customer_first_name,
            "customerLastName": customer_last_name, "description": description})

    async def transfer_natcash(self, *, gdes: int, wallet: str,
                               customer_first_name: Optional[str] = None,
                               customer_last_name: Optional[str] = None) -> dict[str, Any]:
        """Send a NatCash transfer. Returns ``{transactionId, …}``."""
        return await self._post("/natcash/transfers", {
            "gdes": gdes, "wallet": wallet, "customerFirstName": customer_first_name,
            "customerLastName": customer_last_name})

    async def transfer_status(self, transfer_id: str) -> dict[str, Any]:
        """Status of a transfer: ``{status, …}`` (successful/processing/failed)."""
        return await self._get(f"/transfers/{transfer_id}")

    async def quote(self, *, gdes: int, provider: str = "moncash") -> dict[str, Any]:
        """Fee quote before a transfer (provider: 'moncash' | 'natcash')."""
        return await self._post("/transfers/quote", {"gdes": gdes, "provider": provider})

    # ---- wallet ---------------------------------------------------------------
    async def wallet_balance(self) -> dict[str, Any]:
        """Wallet balance in HTG."""
        return await self._get("/wallet")
