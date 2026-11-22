# Group12 — Payment regression tests (standalone)

This suite tests **only Payment**. No existing tests in
`Test/test_cart_booking.py`, `Test/test_auth.py`, or any
`Test/test_vehicle_*.py` have been edited.

## Run just Payment (Windows / VS Code)

From `Project-CNPM/SourceCode`:

```powershell
py -m pip install -r requirements.txt pytest
py -m pytest Test/test_payment_flow.py -v
```

Run all existing tests plus Payment:

```powershell
py -m pytest Test/test_auth.py Test/test_cart_booking.py Test/test_payment_flow.py -v
py -m unittest discover -s Test -p "test_vehicle_*.py" -v
```

The CI pipeline runs the existing Vehicle, Authentication and Cart/Booking steps
**unchanged**, followed by one new Payment-only step.

## Payment test coverage (54 named functions + parameterized cases)

| ID | Scenario |
|---|---|
| TP01–TP09 | E-wallet sandbox deposit, decline, invalid outcomes, removed CARD, Bank Transfer/Cash Pending, amount and balance calculations |
| TP10–TP16 | Unpaid/Pending/Partially Paid/Paid in Full/Cancelled statuses; prevent duplicate remaining requests |
| TP17–TP24 | VietQR amount and bank reference, invalid QR inputs, safe MoMo merchant filename, QR not configured, configured QR displayed |
| TP25–TP35 | Checkout must redirect to Payment first without creating an order; payment success/failure; Cash/Bank Pending; forged CARD; CSRF, expiry, replay, and receipt ownership |
| TP36–TP44 | Remaining 70% blocked before deposit verified; all 3 remaining methods; duplicate/invalid/unauthorized requests; change payment method; QR of exact remaining amount; owner and CSRF protection |
| TP45–TP52 | Admin-only payment confirmation, forged/locked Admin denied, CSRF and staff acknowledgment, initial deposit verification, 70% confirmation exactly once, overpayment blocked, cancellation/refund flags |
| TP53–TP54 | Rollback all booking/payment inserts on transaction failure and preserve previously paid deposit when second insert fails |

**Testing environment:** The suite uses pytest + a transactional in-memory
SQLite adapter already defined by the Booking integration test file to exercise
the application's real SQL/service/Flask code without MySQL or real providers.
It imports those existing fixtures **read-only**. Each case gets isolated data.
These are automated integration tests, not proof of a successful live bank
payment, actual MoMo API callback, or real settlement.

**Important:** The initial E-Wallet demo success is simulated; Bank Transfer
and Cash payment records remain Pending until independently verified by staff.
QR generation is display only. Refund Pending is a manual refund task, not an
actual transfer to the customer.
