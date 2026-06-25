# bazik-sdk (Python)

Tiny **async** Python client for the [Bazik](https://bazik.io) API — **MonCash** payments for Haiti. Production-tested (powers payments on TradeMakaya). One dependency: `httpx`.

## Install

```bash
pip install bazik-sdk
```

## Quick start

```python
import asyncio
from bazik import BazikClient

async def main():
    client = BazikClient(user_id="YOUR_USER_ID", secret_key="YOUR_SECRET_KEY")

    # 1) Create a payment (amount in gourdes, max 75,000 HTG)
    order = await client.create_moncash_payment(
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

    # 2) Check status (or poll until it resolves)
    result = await client.wait_for_completion(order["orderId"], interval=3, timeout=180)
    print("Status:", result["status"])   # "successful" | "pending" | "failed"

asyncio.run(main())
```

## API

| Method | Description |
|---|---|
| `BazikClient(user_id, secret_key, base_url=…, timeout=20)` | Create a client. |
| `await authenticate()` | Fetch & cache a bearer token (auto-called). |
| `await create_moncash_payment(*, gdes, reference_id, …)` | Create a MonCash payment → `{orderId, redirectUrl, …}`. |
| `await verify_payment(order_id)` | Current status → `{status, referenceId, …}`. |
| `await wait_for_completion(order_id, *, interval=3, timeout=180)` | Poll until resolved. |

`create_moncash_payment` optional fields: `webhook_url`, `description`, `customer_first_name`, `customer_last_name`, `customer_email`, `success_url`, `error_url`.

Errors raise `bazik.BazikError` (`.status_code`, `.body`).

> **Note:** the amount field is `gdes` (gourdes) — not `gourdes`. Sending the wrong key creates a payment with no amount.

## Webhook flow

Bazik POSTs `{ orderId }` to your `webhook_url` on a status change. **Don't trust the body** — verify:

```python
verified = await client.verify_payment(order_id)
if verified["status"] == "successful":
    ...  # activate the order
```

## License

MIT © Falandy Jean. Unofficial SDK; not affiliated with Bazik.
