# Group12: Checkout → Payment → Booking result (demo only)

## Three-step user journey

1. **Cart / Book Now:** select cars and rental dates. Book Now does not insert cars into the saved cart.
2. **Checkout:** choose pickup/return locations, receiving method and payment method. Click **Proceed to Payment**. This only saves a short-lived draft in the signed user session: **no order is written to MySQL yet**.
3. **Payment** at `/payment`: see the chosen method, deposit amount and rental summary.
   - **CARD** / **E_WALLET:** choose **Simulate Successful Payment** to approve a demo deposit (30%). The app then creates `Orders`, `Oderitem`, `Payments` in one MySQL transaction and redirects to the customer receipt. Choose **Simulate Failed Payment** to see a failure without creating an order.
   - **BANK_TRANSFER:** a request may be confirmed with payment **Pending**. No bank integration, automatic validation or real transfer is supported.
   - **CASH:** a request may be confirmed with payment **Pending** until cash is collected offline.
   - These offline methods create pending rental requests, **not proof of completed payment**. Genuine payment-success-only bookings for bank transfers require verified provider callbacks, and cash needs staff confirmation.
4. **Success:** a receipt is viewable at `/orders/<id>/payment` only by the booking customer. My Orders shows payment status and remaining balance.

Pending checkout drafts expire after 15 minutes. Payment POST requires a per-draft CSRF token. The backend validates current vehicle status, dates, collision with active rentals and prices again before saving. A successful checkout removes only the purchased items from the cart; a failed attempt leaves the cart alone.

## Run on Windows

```powershell
git fetch origin
git switch feature/vehicle-figma
git pull origin feature/vehicle-figma
cd SourceCode
py -m pip install -r requirements.txt pytest
py run.py
```

Set up `SourceCode/.env` from `.env.example`. Use your local MySQL database on port 3307. Database schema includes `Payments`, `Orders` and `Oderitem`.

Test: register/login, Book Now, Checkout with the chosen payment method, proceed to Payment, simulate failure (no order), then retry and simulate success (order + receipt). For tests:

```powershell
py -m pytest Test/test_cart_booking.py -v
```

**Safety:** All card/e-wallet payments and refund statuses are mock transactions. Never enter real card/CVV or bank credentials. Production requires a PSP hosted checkout + verified webhooks, idempotency, reconciliation, real refunds, admin confirmation for offline methods, and production-grade security controls.
