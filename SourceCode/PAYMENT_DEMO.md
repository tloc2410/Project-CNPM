# Group12: Checkout → Payment → Booking result (demo only)

## Three-step user journey

1. **Cart / Book Now:** select cars and rental dates. Book Now does not insert cars into the saved cart.
2. **Checkout:** choose pickup/return locations, receiving method and payment method. Click **Proceed to Payment**. This only saves a short-lived draft in the signed user session: **no order is written to MySQL yet**.
3. **Payment** at `/payment`: see the chosen method, deposit amount and rental summary.
   - **E_WALLET:** choose **Simulate Successful Payment** to approve a demo deposit (30%). The app then creates `Orders`, `Oderitem`, `Payments` in one MySQL transaction and redirects to the customer receipt. Choose **Simulate Failed Payment** to see a failure without creating an order.
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

**Safety:** All e-wallet payments and refund statuses are mock transactions. Never enter real wallet or bank credentials. The Credit / Debit Card method has been removed from checkout and the payment backend. Production requires a PSP hosted checkout + verified webhooks, idempotency, reconciliation, real refunds, admin confirmation for offline methods, and production-grade security controls.


## Show real recipient QR codes on /payment (optional)

No bank account or merchant QR is committed to this repository. The web page
does not show a scannable receiver QR until the operator configures one.

**Bank transfer (VietQR Quick Link):**

Add the bank recipient details to your LOCAL `SourceCode/.env` (do not commit):

```dotenv
PAYMENT_BANK_BIN=970436
PAYMENT_BANK_ACCOUNT=REPLACE_WITH_REAL_RECEIVER_ACCOUNT
PAYMENT_BANK_HOLDER=REPLACE WITH VERIFIED ACCOUNT HOLDER
```

`PAYMENT_BANK_BIN` is the receiving bank's BIN or supported VietQR code; 970436
is Vietcombank as an EXAMPLE, not a Group12 bank account. Replace account and
name with verified merchant information. The Payment screen generates a VietQR
image from `https://img.vietqr.io/image/<bank>-<account>-compact2.png`,
prefills the **30% deposit** and a random `G12...` payment reference,
and displays the same values as plain text for verification.
A QR image is only a transfer instruction, not evidence funds arrived.

**MoMo static merchant QR:**

1. Register for MoMo For Business and obtain the static QR issued by MoMo
   for the merchant. Do not try to create a MoMo QR by encoding a phone number.
2. Save the merchant-provided image as
   `SourceCode/presentation/static/images/payments/momo-merchant.png`.
3. Set `MOMO_MERCHANT_QR_FILENAME=momo-merchant.png` in local `.env`.
4. Restart Flask and select **E-Wallet** at Checkout. The page displays the
   provided merchant image and the calculated deposit.
5. Static QR codes cannot encode a unique per-order amount/reference or reliably
   notify Group12 when money has been paid. Users may have to enter the amount
   manually. For automatic order-specific MoMo QR and payment verification,
   integrate MoMo's official `/v2/gateway/api/create` + signed IPN/webhook.

**CRITICAL:** The current project's **Simulate Successful Payment** button is
ONLY a fake demo and does not query either the bank or MoMo. Do not use it to
claim a real QR transfer succeeded. To run real payment collection, disable
manual/demo success buttons, store a transaction intent, verify server-to-server
provider notifications and bank settlement, and only THEN finalize an order.
For the present course project, use MoMo sandbox credentials or dummy QR
images, not actual money, unless your group implements official verification.

Docs:
- https://www.vietqr.io/qr-dong
- https://developers.momo.vn/v3/docs/payment/guides/static-qrcode/
- https://developers.momo.vn/v3/docs/payment/api/wallet/onetime/


## Second payment: remaining 70% (integrated feature)

The existing `Payments` table stores more than one row per rental booking:
the initial deposit (30%), then a separate remaining-balance payment request.
No new MySQL schema is required; do not re-run the original database setup.

**Customer flow:**

1. Make a booking. E-wallet **demo** deposit is recorded Paid. Bank transfer
   deposit is Pending until staff verifies actual receipt. For Cash on Delivery,
   the full amount is Pending until collected at pickup.
2. From **My Account → My Rentals**, **My Orders**, or the receipt, open
   **Pay Remaining Balance** (`/orders/<id>/pay-remaining`).
3. The form becomes available only after the deposit has been verified as Paid,
   the booking is active and no other payment request is pending.
4. Choose **E-Wallet (MoMo)**, **Bank Transfer (VietQR)**, or **Cash at Pickup**.
   Submit to create an exact-balance **Pending** payment row (reference `BAL-...`).
   VietQR includes the remaining amount and unique reference; MoMo uses the
   authorized merchant image (manual amount entry); Cash is collected in person.
5. Pending transfers do **not** count as Paid. Admin must verify receipt.
   Customers can cancel an unverified balance request to change the method.
6. The receipt shows the deposit, paid sum, pending sum, remaining amount, and
   both payment records. Fully received orders display **Paid in Full**.

**Administrator flow:**

1. Sign into a real account with `role='ADMIN'` and `isLocked=0` in Users.
2. In the user menu choose **Admin Payments**, or navigate to
   `/admin/payments`.
3. The queue shows pending initial deposits, cash payments and `BAL-...`
   remaining requests, including customer, amount and transfer reference.
4. Confirm the exact amount in the actual bank/wallet/cash ledger first.
5. Tick verification acknowledgement and click **Confirm Received**.
6. The backend locks the order, checks payment is still Pending and total paid
   will not exceed the order total, marks only that payment Paid with timestamp,
   and commits. Verifying the first deposit also confirms a pending booking.
   Repeated confirmations cannot credit the transaction twice.

**Business example:** Rental = 500,000 VND; deposit = 150,000 VND; after
verification the remaining payment request is 350,000 VND. When the admin
verifies the 350,000 VND, paid total becomes 500,000 VND, outstanding = 0.

**Limitations:** Customer and admin pages cannot check a live bank/MoMo
transaction automatically. A screenshot, scanned QR, or clicking "I paid" is
not bank reconciliation. Admin confirmation is a manual demo workflow.
Cash collection is physically checked by staff. The initial E-Wallet deposit
may still be a sandbox simulated Paid amount; it must not be represented as
real funds. Production must replace mock approvals with signed provider
callbacks, ledger reconciliation, refund handling and audited staff actions.
Cancellation marks verified payments `Refund Pending` (not automatically
refunded); pending requests become `Cancelled`.

**Test:** from `SourceCode` run
`py -m pytest Test/test_cart_booking.py -v`. Payment, admin permissions, role
recheck, cross-account access, duplicate request/confirmation, QR amounts,
cancellation and rollback are covered by SQLite-backed integration tests.
