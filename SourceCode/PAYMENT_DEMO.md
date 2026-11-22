# Group12 Booking + Payment integration (sandbox only)

## What works

- Cart Checkout and Book Now continue using the current Booking implementation.
- The Booking service recomputes authoritative prices using MySQL, checks vehicle availability and rental date overlaps, and locks cars before creating the order.
- One database transaction inserts **Orders**, **Oderitem** and **Payments**. If any insert fails, every row rolls back. A simulated card/e-wallet decline also rolls back the entire booking and preserves cart items.
- Payment methods match the Booking form values: `CARD`, `E_WALLET`, `BANK_TRANSFER`, `CASH`.
- Card / wallet: **sandbox simulation**, marks 30% deposit as `Paid` in the project database. Choose the simulated decline option to verify failure. **No real funds move.**
- Bank transfer: 30% deposit recorded as `Pending`, awaiting manual verification. The app does not provide bank details or automatically verify a transfer.
- Cash: full booking price recorded as `Pending`; payable to the rental operator offline.
- The customer may view payment status and order-specific receipt at `/orders/<order_id>/payment`. Access is restricted to the account that owns the order.
- Cancel a pending/confirmed booking: `Pending` payment changes to `Cancelled`. Simulated `Paid` changes to `Refunded` in the DB only: **no actual refund takes place**.
- Payment amounts and remaining balances are displayed on My Orders and the receipt.

## Setup on Windows

1. Checkout `feature/vehicle-figma`; run `git pull`.
2. In `SourceCode`, run `py -m pip install -r requirements.txt pytest`.
3. Copy `.env.example` to `.env`; configure MySQL 8.4 at port 3307 and your local credentials.
4. Import `Database/group12_car_rental.sql` into MySQL once if not created, then optionally run `Database/booking_setup.sql` to add demonstration vehicles.
5. Run `py run.py`. Sign in, choose a vehicle, add to cart or Book Now, proceed through Checkout, select a demo payment method, then view My Orders and Payment Receipt.
6. Run `py -m pytest Test/test_cart_booking.py -v` from the `SourceCode` folder to verify integration with transactional SQLite, including rollback and access protection.

## Not a production payment gateway

This work does NOT collect or validate card numbers, CVVs or bank details and does NOT integrate a card processor, MoMo, ZaloPay or a bank. UI choices are for functional demonstration only. Never enter real credentials. Before production: integrate a payment service provider's hosted checkout, verified server-side webhooks, idempotency keys, reconciliation, authenticated admin verification for offline bank transfers, real refunds, CSRF protection on writes, and secure logging.
