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
