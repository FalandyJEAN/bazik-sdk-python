# bazik-sdk (Python)

[![PyPI](https://img.shields.io/pypi/v/bazik-sdk.svg)](https://pypi.org/project/bazik-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/bazik-sdk.svg)](https://pypi.org/project/bazik-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Async **Python** client for the [Bazik](https://bazik.io) API — **MonCash & NatCash** payments, payouts, transfers and wallet for Haiti 🇭🇹. Fully typed, one dependency (`httpx`), production-tested.

## Install

```bash
pip install bazik-sdk
```

## Quick start

```python
import asyncio
from bazik import BazikClient, STATUS_SUCCESSFUL

async def main():
    async with BazikClient(user_id="YOUR_USER_ID", secret_key="YOUR_SECRET_KEY") as bazik:
        # Create a MonCash payment (amount in gourdes, max 75,000 HTG)
        order = await bazik.create_moncash_payment(
            gdes=500,
            reference_id="INV-1001",
            description="Pro plan",
            customer_first_name="Jean",
            customer_last_name="Pierre",
            customer_email="jean@example.com",
            webhook_url="https://api.yoursite.com/billing/moncash/webhook",
            success_url="https://yoursite.com/paid",
            error_url="https://yoursite.com/canceled",
        )
        print("Send the customer to:", order["redirectUrl"])

        # Poll until it resolves
        result = await bazik.wait_for_completion(order["orderId"], interval=3, timeout=180)
        print("Paid!" if result.get("status") == STATUS_SUCCESSFUL else result.get("status"))

asyncio.run(main())
```

> `BazikClient` works both as an `async with` context manager (reuses one connection pool)
> and standalone — call `await bazik.aclose()` when you're done.

## API reference

### Payments
| Method | HTTP | Description |
|---|---|---|
| `create_moncash_payment(*, gdes, reference_id, webhook_url=…, description=…, customer_first_name=…, customer_last_name=…, customer_email=…, success_url=…, error_url=…)` | `POST /moncash/token` | Create a MonCash payment → `{orderId, redirectUrl, status}` |
| `verify_payment(order_id)` | `GET /order/{id}` | Current status → `{status, referenceId, …}` |
| `is_paid(order_id)` | — | `True` if status == `successful` |
| `wait_for_completion(order_id, *, interval=3, timeout=180)` | — | Poll until resolved |
| `withdraw(*, gdes, wallet, description=…)` | `POST /moncash/withdraw` | Payout to a MonCash wallet |
| `get_balance()` | `GET /balance` | Account balance `{available, reserved}` |

### Transfers
| Method | HTTP | Description |
|---|---|---|
| `check_customer(wallet)` | `POST /moncash/customers/status` | KYC status of a wallet |
| `transfer_moncash(*, gdes, wallet, customer_first_name=…, customer_last_name=…, description=…)` | `POST /moncash/transfers` | MonCash transfer → `{transactionId}` |
| `transfer_natcash(*, gdes, wallet, customer_first_name=…, customer_last_name=…)` | `POST /natcash/transfers` | NatCash transfer → `{transactionId}` |
| `transfer_status(transfer_id)` | `GET /transfers/{id}` | Transfer status |
| `quote(*, gdes, provider="moncash")` | `POST /transfers/quote` | Fee quote before a transfer |

### Wallet & auth
| Method | HTTP | Description |
|---|---|---|
| `wallet_balance()` | `GET /wallet` | Wallet balance (HTG) |
| `authenticate()` | `POST /token` | Fetch & cache a bearer token (auto-called) |

Status constants: `STATUS_PENDING`, `STATUS_SUCCESSFUL`, `STATUS_FAILED`, `STATUS_CANCELLED`.
Errors raise `bazik.BazikError` with `.status_code` and `.body`.

> **Amount field is `gdes`** (gourdes) — never `gourdes`. The wrong key creates a payment with no amount.

## Webhook verification (don't trust the body)

Bazik POSTs `{ orderId }` to your `webhook_url`. Always re-verify before fulfilling:

```python
async def webhook(payload: dict, bazik: BazikClient):
    order_id = payload.get("orderId")
    if order_id and await bazik.is_paid(order_id):
        ...  # activate the order
```

## Examples

```python
# Payout 250 HTG to a wallet
await bazik.withdraw(gdes=250, wallet="509xxxxxxxx", description="Refund")

# Quote fees, then transfer
q = await bazik.quote(gdes=1000, provider="moncash")
tx = await bazik.transfer_moncash(gdes=1000, wallet="509xxxxxxxx", customer_first_name="Marie")
print(await bazik.transfer_status(tx["transactionId"]))

# Balances
print(await bazik.get_balance())     # account
print(await bazik.wallet_balance())  # wallet
```

## License

MIT © Falandy Jean. Unofficial SDK — not affiliated with Bazik.
