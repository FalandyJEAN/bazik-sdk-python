# Changelog

## 0.2.0
- Full API coverage: `withdraw`, `get_balance`, `check_customer`, `transfer_moncash`,
  `transfer_natcash`, `transfer_status`, `quote`, `wallet_balance`.
- `is_paid()` convenience + status constants (`STATUS_*`).
- Reusable connection pool via async context manager (`async with`) + `aclose()`.
- Typed package (`py.typed`), PyPI classifiers, richer docs.

## 0.1.0
- Initial release: `authenticate`, `create_moncash_payment`, `verify_payment`,
  `wait_for_completion`.
