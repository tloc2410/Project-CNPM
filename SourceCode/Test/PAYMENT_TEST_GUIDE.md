# Group12 — Payment test guide (short version)

The Payment suite is now **20 focused test functions**, reduced from 54.
With parameterized inputs it runs **24 test cases** in pytest.

Only `Test/test_payment_flow.py` was shortened. No existing tests in
`Test/test_cart_booking.py`, `Test/test_auth.py`, or
`Test/test_vehicle_*.py` were changed. The CI commands for these
existing suites are also unchanged.

## Run Payment tests in VS Code

Open terminal inside `Project-CNPM/SourceCode`:

```powershell
py -m pip install -r requirements.txt pytest
py -m pytest Test/test_payment_flow.py -v
```

## Core scenarios

| Test | Check |
|---|---|
| TP01–TP02 | Bank deposit = 30% Pending; Cash = full amount Pending |
| TP03–TP04 | VietQR amount/reference; MoMo QR appears only with merchant image |
| TP05–TP09 | Checkout draft before payment; declined payment does not create booking; success/receipt; CSRF; replay |
| TP10–TP13 | Deposit confirmation required before 70%; correct remaining amount for wallet/bank/cash; no duplicate request; QR for remainder |
| TP14–TP18 | Fake Admin blocked; CSRF/acknowledgment required; deposit verified; balance Paid in Full exactly once; cancel/refund needs manual review |
| TP19–TP20 | Initial and remaining-payment database errors correctly roll back |

This is intentionally shorter and concentrates on the most important
positive/negative payment paths. Less common edge cases remain covered by
the existing untouched Cart/Booking integration test suite.

**Scope:** Test fixtures use transactional SQLite/Flask rather than an
external bank, MoMo production API or real MySQL instance. E-wallet approval
is only a sandbox demo, and QR display does not verify receipt of money.
