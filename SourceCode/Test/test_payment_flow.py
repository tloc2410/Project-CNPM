"""Payment-only regression suite for Group12 Car Rental.

PURPOSE
-------
Covers initial 30% deposit, remaining 70%, demo checkout, QR display,
transaction persistence, staff verification, security, and refund flags.

SCOPE
-----
This is a NEW payment-only file. Existing Authentication, Vehicle and
Cart/Booking test files are not changed. Reuses the read-only SQLite/Flask
test fixtures already provided by test_cart_booking.py so this suite runs
without a real MySQL server, gateway credentials or actual bank transfers.

IMPORTANT: E-wallet Paid on initial checkout is a simulated demo result;
QR display never proves money was transferred. Real collections require
provider verification or a staff member who checked actual bank/cash ledgers.
"""
import re
import time
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from business import booking_service as booking
from business import payment_service as pay
from business import payment_collection_service as collect
from business import payment_qr as qr
from data import payment_repository
from test_cart_booking import booking_db, flask_client, _login_session


def _item(offset=20, rental_days=1):
    pickup = date.today() + timedelta(days=offset)
    end = pickup + timedelta(days=rental_days)
    return {
        "car_id": 1, "pickup_date": pickup.isoformat(),
        "return_date": end.isoformat(), "selected": True,
    }


def _order(method="E_WALLET", offset=20):
    return booking.place_order(1, [_item(offset)], "PICKUP", method)


def _checkout(client, method="E_WALLET", offset=25):
    _login_session(client)
    entry = _item(offset)
    response = client.post("/cart/add/1", data={
        "pickup_date": entry["pickup_date"], "return_date": entry["return_date"]
    })
    assert response.status_code == 302
    result = client.post("/checkout", data={
        "pickup_date": entry["pickup_date"],
        "return_date": entry["return_date"],
        "payment_method": method,
        "receiving_method": "PICKUP",
        "agree_terms": "on",
    })
    assert result.status_code == 302
    assert result.headers["Location"].endswith("/payment")
    with client.session_transaction() as sess:
        return sess["pending_payment"]["csrf"]


def _staff(raw, client, user_id=3, locked=0):
    raw.execute(
        """INSERT INTO Users(UserID, fullName, phone, email, passwordHash, role, isLocked)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, "Payment Staff", "0900000000", "staff@example.test",
         "test-hash", "ADMIN", locked),
    )
    _login_session(client, user_id=user_id, full_name="Payment Staff")
    with client.session_transaction() as sess:
        sess["role"] = "ADMIN"


def _balance_token(client, order_id):
    response = client.get(f"/orders/{order_id}/pay-remaining")
    assert response.status_code == 200
    with client.session_transaction() as sess:
        return sess["collection_csrf"]


def _pending_id(raw, order_id):
    return raw.execute(
        """SELECT paymentID FROM Payments
           WHERE oderID = ? AND paymentStatus = 'Pending'
           ORDER BY paymentID DESC LIMIT 1""", (order_id,),
    ).fetchone()[0]


# PAYMENT RULES -------------------------------------------------------------

def test_payment_01_wallet_deposit_is_paid_demo_only():
    plan = pay.plan_payment("E_WALLET", 8, Decimal("500000"), Decimal("150000"))
    assert plan.amount == Decimal("150000")
    assert plan.status == "Paid"
    assert plan.transaction_code.startswith("DEMO-8-")
    assert plan.paid_at is not None


def test_payment_02_wallet_decline_does_not_create_payment_plan():
    with pytest.raises(pay.PaymentError, match="declined"):
        pay.plan_payment("E_WALLET", 1, 500000, 150000, "declined")


@pytest.mark.parametrize("outcome", ["cancel", "failure", "pending", "", None])
def test_payment_03_wallet_rejects_unrecognized_demo_result(outcome):
    with pytest.raises(pay.PaymentError, match="Invalid test payment result"):
        pay.plan_payment("E_WALLET", 1, 500000, 150000, outcome)


@pytest.mark.parametrize("method", ["CARD", "CRYPTO", "MOMO_PERSONAL", "", None])
def test_payment_04_only_supported_payment_methods_are_accepted(method):
    with pytest.raises(pay.PaymentError, match="Invalid payment method"):
        pay.plan_payment(method, 1, 500000, 150000)


def test_payment_05_bank_deposit_pending_with_reference():
    plan = pay.plan_payment(
        "BANK_TRANSFER", 7, 500000, 150000, transfer_reference="G12TEST7"
    )
    assert plan.amount == Decimal("150000")
    assert plan.status == "Pending"
    assert plan.transaction_code == "G12TEST7"
    assert plan.paid_at is None


def test_payment_06_bank_reference_default_for_older_bookings():
    assert pay.plan_payment("BANK_TRANSFER", 9, 500000, 150000).transaction_code == "G12-9"


def test_payment_07_cash_full_amount_pending_at_pickup():
    plan = pay.plan_payment("CASH", 5, 500000, 150000)
    assert plan.status == "Pending"
    assert plan.amount == Decimal("500000")
    assert plan.paid_at is None


@pytest.mark.parametrize("status,expected", [
    ("Paid", "350000"), ("Pending", "500000"),
    ("Refund Pending", "500000"), ("Cancelled", "500000"),
])
def test_payment_08_pending_is_not_counted_as_received(status, expected):
    assert pay.balance_due(500000, status, 150000) == Decimal(expected)


def test_payment_09_balance_is_never_negative():
    assert pay.balance_due(500000, "Paid", 600000) == Decimal("0")


def test_payment_10_unpaid_order_without_records():
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "PENDING"}, []
    )
    assert view["paid_amount"] == 0
    assert view["balance_due"] == 500000
    assert view["payment_status"] == "Unpaid"
    assert not view["can_pay_remaining"]


def test_payment_11_pending_deposit_still_owes_full_total():
    payments = [{
        "paymentStatus": "Pending", "amount": 150000,
        "transactionCode": "G12TEST", "paymentID": 1,
    }]
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "PENDING"}, payments
    )
    assert view["pending_amount"] == 150000
    assert view["paid_amount"] == 0
    assert view["balance_due"] == 500000
    assert view["payment_status"] == "Awaiting Verification"
    assert not view["can_pay_remaining"]


def test_payment_12_verified_deposit_allows_exact_70_percent_remainder():
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "CONFIRMED"},
        [{"paymentStatus": "Paid", "amount": 150000,
          "transactionCode": "DEMO-7", "paymentID": 1}],
    )
    assert view["paid_amount"] == 150000
    assert view["balance_due"] == 350000
    assert view["payment_status"] == "Partially Paid"
    assert view["can_pay_remaining"]


def test_payment_13_paid_in_full_requires_two_verified_payments():
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "CONFIRMED"},
        [
            {"paymentStatus": "Paid", "amount": 150000, "paymentID": 1},
            {"paymentStatus": "Paid", "amount": 350000, "paymentID": 2},
        ],
    )
    assert view["payment_status"] == "Paid in Full"
    assert view["balance_due"] == 0
    assert not view["can_pay_remaining"]


def test_payment_14_cancelled_order_cannot_accept_remaining_payment():
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "CANCELLED"},
        [{"paymentStatus": "Paid", "amount": 150000, "paymentID": 1}],
    )
    assert view["payment_status"] == "Cancelled"
    assert not view["can_pay_remaining"]


def test_payment_15_refund_pending_does_not_increase_paid_amount():
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "CANCELLED"},
        [{"paymentStatus": "Refund Pending", "amount": 150000, "paymentID": 1}],
    )
    assert view["paid_amount"] == 0
    assert view["balance_due"] == 500000


def test_payment_16_pending_remaining_blocks_another_request():
    view = collect.payment_overview(
        {"totalPrice": 500000, "deposit": 150000, "status": "PENDING"},
        [
            {"paymentStatus": "Paid", "amount": 150000, "paymentID": 1},
            {"paymentStatus": "Pending", "amount": 350000,
             "transactionCode": "BAL-7-X", "paymentID": 2},
        ],
    )
    assert view["pending_amount"] == 350000
    assert view["balance_due"] == 350000
    assert view["pending_balance_request"]["paymentID"] == 2
    assert not view["can_pay_remaining"]


# BANK & MOMO QR ------------------------------------------------------------

def test_payment_17_vietqr_encodes_deposit_and_reference(monkeypatch):
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "GROUP12 DEMO")
    url = qr.bank_transfer_qr(150000, "G12DEMO123")
    assert url.startswith("https://img.vietqr.io/image/970436-0000000000-compact2.png?")
    params = parse_qs(urlparse(url).query)
    assert params["amount"] == ["150000"]
    assert params["addInfo"] == ["G12DEMO123"]
    assert params["accountName"] == ["GROUP12 DEMO"]


def test_payment_18_vietqr_accepts_unique_balance_reference(monkeypatch):
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")
    url = qr.bank_transfer_qr(350000, "BAL-7-ABCDEF1234")
    params = parse_qs(urlparse(url).query)
    assert params["amount"] == ["350000"]
    assert params["addInfo"] == ["BAL-7-ABCDEF1234"]


@pytest.mark.parametrize("bank,account,amount,ref", [
    ("", "0000000000", 150000, "G12TEST"),
    ("970436", "", 150000, "G12TEST"),
    ("970436", "../hack", 150000, "G12TEST"),
    ("bad-bank!", "0000000000", 150000, "G12TEST"),
    ("970436", "0000000000", 0, "G12TEST"),
    ("970436", "0000000000", -1, "G12TEST"),
    ("970436", "0000000000", "oops", "G12TEST"),
    ("970436", "0000000000", 150000, "../bad"),
])
def test_payment_19_vietqr_rejects_missing_or_invalid_inputs(
    monkeypatch, bank, account, amount, ref
):
    monkeypatch.setenv("PAYMENT_BANK_BIN", bank)
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", account)
    assert qr.bank_transfer_qr(amount, ref) is None


@pytest.mark.parametrize("filename", [
    "../payment.png", "/tmp/merchant.png", "..\\merchant.png",
    ".env", "code.svg", "fake.gif", "",
])
def test_payment_20_momo_rejects_untrusted_or_unsupported_filename(monkeypatch, filename):
    monkeypatch.setenv("MOMO_MERCHANT_QR_FILENAME", filename)
    assert qr.momo_merchant_qr_filename() is None


def test_payment_21_momo_accepts_merchant_image_filename(monkeypatch):
    monkeypatch.setenv("MOMO_MERCHANT_QR_FILENAME", "momo-merchant.png")
    assert qr.momo_merchant_qr_filename() == "momo-merchant.png"


def test_payment_22_bank_page_without_recipient_does_not_show_qr(
    flask_client, booking_db, monkeypatch
):
    for key in ("PAYMENT_BANK_BIN", "PAYMENT_BANK_ACCOUNT", "PAYMENT_BANK_HOLDER"):
        monkeypatch.delenv(key, raising=False)
    _checkout(flask_client, "BANK_TRANSFER")
    page = flask_client.get("/payment")
    assert page.status_code == 200
    assert b"Bank QR is not configured yet" in page.data
    assert b"img.vietqr.io" not in page.data
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


def test_payment_23_bank_page_configured_shows_deposit_not_full_total(
    flask_client, booking_db, monkeypatch
):
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "TEST PAYEE")
    _checkout(flask_client, "BANK_TRANSFER")
    page = flask_client.get("/payment").get_data(as_text=True)
    assert "img.vietqr.io/image/970436-0000000000-compact2.png" in page
    assert "amount=180000" in page
    assert "G12" in page


def test_payment_24_momo_page_requires_existing_merchant_qr_file(
    flask_client, booking_db, monkeypatch, tmp_path
):
    import run
    monkeypatch.setenv("MOMO_MERCHANT_QR_FILENAME", "momo-test.png")
    _checkout(flask_client)
    html = flask_client.get("/payment").get_data(as_text=True)
    assert "MoMo QR is not configured yet" in html
    folder = tmp_path / "images" / "payments"
    folder.mkdir(parents=True)
    (folder / "momo-test.png").write_bytes(b"test-only-not-real-qr")
    monkeypatch.setattr(run.app, "static_folder", str(tmp_path))
    updated = flask_client.get("/payment").get_data(as_text=True)
    assert "/static/images/payments/momo-test.png" in updated
    assert "MoMo merchant QR" in updated


# SEPARATE CHECKOUT -> PAYMENT STEP ----------------------------------------

def test_payment_25_checkout_stages_draft_without_order_or_payment(
    flask_client, booking_db
):
    _checkout(flask_client)
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 0
    assert b"Complete Your Payment" in flask_client.get("/payment").data


def test_payment_26_demo_decline_keeps_cart_and_creates_no_order(
    flask_client, booking_db
):
    token = _checkout(flask_client)
    page = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "declined",
    })
    assert page.status_code == 200
    assert b"No order was placed" in page.data
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 0
    with flask_client.session_transaction() as sess:
        assert len(sess["rental_cart"]) == 1


def test_payment_27_wallet_confirmation_saves_deposit_and_receipt(
    flask_client, booking_db
):
    token = _checkout(flask_client, "E_WALLET")
    result = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert result.status_code == 302
    assert re.search(r"/orders/\d+/payment$", result.headers["Location"])
    raw, _ = booking_db
    row = raw.execute(
        "SELECT oderID, amount, paymentStatus, paymentMethod FROM Payments"
    ).fetchone()
    assert row["amount"] == 180000
    assert row["paymentStatus"] == "Paid"
    assert row["paymentMethod"] == "E_WALLET"
    assert b"Payment History" in flask_client.get(result.headers["Location"]).data


def test_payment_28_bank_confirmation_is_pending_not_paid(
    flask_client, booking_db
):
    token = _checkout(flask_client, "BANK_TRANSFER")
    with flask_client.session_transaction() as sess:
        transfer_reference = sess["pending_payment"]["transfer_reference"]
    result = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert result.status_code == 302
    raw, _ = booking_db
    row = raw.execute(
        "SELECT amount, paymentStatus, transactionCode FROM Payments"
    ).fetchone()
    assert row["amount"] == 180000
    assert row["paymentStatus"] == "Pending"
    assert row["transactionCode"] == transfer_reference
    assert booking.get_order_payment_details(1, 1)["balance_due"] == 600000


def test_payment_29_cash_confirmation_is_pending_for_entire_amount(
    flask_client, booking_db
):
    token = _checkout(flask_client, "CASH")
    flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    raw, _ = booking_db
    row = raw.execute("SELECT amount, paymentStatus FROM Payments").fetchone()
    assert row["amount"] == 600000
    assert row["paymentStatus"] == "Pending"


def test_payment_30_unsupported_card_method_cannot_start_checkout(
    flask_client, booking_db
):
    _login_session(flask_client)
    entry = _item()
    flask_client.post("/cart/add/1", data={
        "pickup_date": entry["pickup_date"],
        "return_date": entry["return_date"],
    })
    rejected = flask_client.post("/checkout", data={
        "pickup_date": entry["pickup_date"],
        "return_date": entry["return_date"],
        "receiving_method": "PICKUP",
        "payment_method": "CARD",
        "agree_terms": "on",
    })
    assert rejected.status_code == 302
    assert "/checkout" in rejected.headers["Location"]
    with flask_client.session_transaction() as sess:
        assert "pending_payment" not in sess


@pytest.mark.parametrize("action", ["confirm", "declined", "mystery"])
def test_payment_31_bad_csrf_never_commits_checkout(
    flask_client, booking_db, action
):
    _checkout(flask_client)
    rejected = flask_client.post("/payment", data={
        "payment_csrf": "forged", "payment_action": action,
    })
    assert rejected.status_code == 400
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


def test_payment_32_invalid_action_never_commits_checkout(
    flask_client, booking_db
):
    token = _checkout(flask_client)
    rejected = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "not-a-payment",
    })
    assert rejected.status_code == 400
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


def test_payment_33_expired_checkout_cannot_charge_or_create_order(
    flask_client, booking_db
):
    token = _checkout(flask_client)
    with flask_client.session_transaction() as sess:
        sess["pending_payment"] = {
            **sess["pending_payment"], "created_at": int(time.time()) - 3600
        }
    response = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert response.status_code == 302
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 0


def test_payment_34_successful_payment_post_cannot_be_replayed(
    flask_client, booking_db
):
    token = _checkout(flask_client)
    payload = {"payment_csrf": token, "payment_action": "confirm"}
    assert flask_client.post("/payment", data=payload).status_code == 302
    assert flask_client.post("/payment", data=payload).status_code == 302
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 1
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1


def test_payment_35_receipt_is_only_visible_to_booking_owner(
    flask_client, booking_db
):
    order_id = _order()
    _login_session(flask_client, user_id=2)
    assert flask_client.get(f"/orders/{order_id}/payment").status_code == 404
    _login_session(flask_client)
    assert flask_client.get(f"/orders/{order_id}/payment").status_code == 200


# REMAINING 70% -------------------------------------------------------------

def test_payment_36_unverified_bank_deposit_blocks_second_payment(booking_db):
    raw, _ = booking_db
    order_id = _order("BANK_TRANSFER")
    with pytest.raises(collect.CollectionError, match="deposit must be verified"):
        collect.request_remaining_payment(1, order_id, "CASH")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1


@pytest.mark.parametrize("method", ["E_WALLET", "BANK_TRANSFER", "CASH"])
def test_payment_37_remaining_request_is_exact_unpaid_amount(booking_db, method):
    raw, _ = booking_db
    order_id = _order()
    payment_id = collect.request_remaining_payment(1, order_id, method)
    row = raw.execute(
        "SELECT amount, paymentStatus, paymentMethod, transactionCode "
        "FROM Payments WHERE paymentID = ?", (payment_id,),
    ).fetchone()
    assert row["amount"] == 420000
    assert row["paymentStatus"] == "Pending"
    assert row["paymentMethod"] == method
    assert row["transactionCode"].startswith("BAL-")
    overview = booking.get_order_payment_details(1, order_id)
    assert overview["paid_amount"] == 180000
    assert overview["pending_amount"] == 420000
    assert overview["balance_due"] == 420000


def test_payment_38_duplicate_remaining_request_is_rejected(booking_db):
    raw, _ = booking_db
    order_id = _order()
    collect.request_remaining_payment(1, order_id, "BANK_TRANSFER")
    with pytest.raises(collect.CollectionError, match="awaiting verification"):
        collect.request_remaining_payment(1, order_id, "CASH")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 2


@pytest.mark.parametrize("method", ["CARD", "PAYPAL", "", None])
def test_payment_39_remaining_rejects_unsupported_payment_method(booking_db, method):
    order_id = _order()
    with pytest.raises(collect.CollectionError, match="valid remaining payment method"):
        collect.request_remaining_payment(1, order_id, method)


def test_payment_40_other_customer_cannot_request_balance(booking_db):
    raw, _ = booking_db
    order_id = _order()
    with pytest.raises(collect.CollectionError, match="not found"):
        collect.request_remaining_payment(2, order_id, "E_WALLET")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1


def test_payment_41_customer_can_cancel_unpaid_request_then_change_method(booking_db):
    raw, _ = booking_db
    order_id = _order()
    old_id = collect.request_remaining_payment(1, order_id, "E_WALLET")
    assert collect.cancel_remaining_request(1, order_id)
    state = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID = ?", (old_id,),
    ).fetchone()[0]
    assert state == "Cancelled"
    new_id = collect.request_remaining_payment(1, order_id, "CASH")
    assert new_id != old_id


def test_payment_42_missing_balance_request_cannot_be_cancelled(booking_db):
    order_id = _order()
    with pytest.raises(collect.CollectionError, match="no pending"):
        collect.cancel_remaining_request(1, order_id)


def test_payment_43_bank_balance_page_shows_qr_of_70_percent(
    flask_client, booking_db, monkeypatch
):
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "TEST PAYEE")
    order_id = _order()
    collect.request_remaining_payment(1, order_id, "BANK_TRANSFER")
    _login_session(flask_client)
    view = flask_client.get(f"/orders/{order_id}/pay-remaining").get_data(as_text=True)
    assert "img.vietqr.io/image/970436-0000000000-compact2.png" in view
    assert "amount=420000" in view
    assert "BAL-" in view
    assert "Awaiting Verification" in view


def test_payment_44_remaining_payment_route_requires_owner_and_csrf(
    flask_client, booking_db
):
    order_id = _order()
    assert flask_client.get(f"/orders/{order_id}/pay-remaining").status_code == 302
    _login_session(flask_client, user_id=2)
    assert flask_client.get(f"/orders/{order_id}/pay-remaining").status_code == 404
    _login_session(flask_client)
    token = _balance_token(flask_client, order_id)
    forged = flask_client.post(f"/orders/{order_id}/pay-remaining", data={
        "csrf_token": "wrong", "action": "request", "payment_method": "CASH",
    })
    assert forged.status_code == 400
    valid = flask_client.post(f"/orders/{order_id}/pay-remaining", data={
        "csrf_token": token, "action": "request", "payment_method": "CASH",
    })
    assert valid.status_code == 302


# ADMIN VERIFICATION --------------------------------------------------------

def test_payment_45_customer_cannot_open_admin_payment_queue(
    flask_client, booking_db
):
    _login_session(flask_client)
    assert flask_client.get("/admin/payments").status_code == 403


def test_payment_46_session_admin_spoof_fails_database_role_check(
    flask_client, booking_db
):
    _login_session(flask_client)
    with flask_client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    assert flask_client.get("/admin/payments").status_code == 403


def test_payment_47_locked_admin_cannot_verify_payment(
    flask_client, booking_db
):
    raw, _ = booking_db
    _staff(raw, flask_client, locked=1)
    assert flask_client.get("/admin/payments").status_code == 403


def test_payment_48_admin_verification_needs_valid_csrf_and_acknowledgment(
    flask_client, booking_db
):
    raw, _ = booking_db
    order_id = _order("BANK_TRANSFER")
    payment_id = _pending_id(raw, order_id)
    _staff(raw, flask_client)
    assert flask_client.get("/admin/payments").status_code == 200
    with flask_client.session_transaction() as sess:
        token = sess["admin_payment_csrf"]
    route = f"/admin/payments/{payment_id}/confirm"
    assert flask_client.post(route, data={
        "csrf_token": "invalid", "verified": "yes",
    }).status_code == 400
    assert flask_client.post(route, data={
        "csrf_token": token,
    }).status_code == 302
    row = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID = ?", (payment_id,),
    ).fetchone()
    assert row["paymentStatus"] == "Pending"


def test_payment_49_staff_verified_deposit_confirms_order(booking_db):
    raw, _ = booking_db
    order_id = _order("BANK_TRANSFER")
    payment_id = _pending_id(raw, order_id)
    assert collect.confirm_collection(payment_id) == order_id
    assert raw.execute(
        "SELECT status FROM Orders WHERE oderID = ?", (order_id,),
    ).fetchone()[0] == "CONFIRMED"
    view = booking.get_order_payment_details(1, order_id)
    assert view["balance_due"] == 420000
    assert view["can_pay_remaining"]


def test_payment_50_staff_verified_balance_marks_paid_in_full_once(booking_db):
    raw, _ = booking_db
    order_id = _order()
    payment_id = collect.request_remaining_payment(1, order_id, "CASH")
    assert collect.confirm_collection(payment_id) == order_id
    with pytest.raises(collect.CollectionError, match="not Pending"):
        collect.confirm_collection(payment_id)
    view = booking.get_order_payment_details(1, order_id)
    assert view["paid_amount"] == 600000
    assert view["balance_due"] == 0
    assert view["payment_status"] == "Paid in Full"
    assert len(view["payments"]) == 2


def test_payment_51_confirm_rejects_amount_exceeding_rental_price(booking_db):
    raw, _ = booking_db
    order_id = _order()
    raw.execute(
        """INSERT INTO Payments
           (oderID, amount, paymentMethod, paymentStatus, transactionCode)
           VALUES (?, ?, ?, ?, ?)""",
        (order_id, 900000, "CASH", "Pending", "BAL-OVERPAY"),
    )
    payment_id = raw.execute("SELECT MAX(paymentID) FROM Payments").fetchone()[0]
    with pytest.raises(collect.CollectionError, match="exceeds"):
        collect.confirm_collection(payment_id)
    assert raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID = ?", (payment_id,),
    ).fetchone()[0] == "Pending"


def test_payment_52_cancellation_requires_manual_refund_not_fake_refunded(booking_db):
    raw, _ = booking_db
    order_id = _order()
    collect.request_remaining_payment(1, order_id, "BANK_TRANSFER")
    booking.cancel_order(1, order_id)
    rows = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE oderID = ? ORDER BY paymentID",
        (order_id,),
    ).fetchall()
    assert [x[0] for x in rows] == ["Refund Pending", "Cancelled"]


# DATABASE TRANSACTION ROLLBACK --------------------------------------------

def test_payment_53_failed_initial_payment_insert_rolls_back_everything(
    booking_db, monkeypatch
):
    raw, track = booking_db
    def simulate_failure(*args, **kwargs):
        raise RuntimeError("payment database offline")
    monkeypatch.setattr(payment_repository, "insert_payment", simulate_failure)
    with pytest.raises(booking.BookingError, match="ROLLBACK"):
        _order()
    assert track["rollbacks"] >= 1
    for table in ("Orders", "Oderitem", "Payments"):
        assert raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_payment_54_failed_remaining_insert_leaves_original_deposit_unchanged(
    booking_db, monkeypatch
):
    raw, track = booking_db
    order_id = _order()
    initial = raw.execute(
        "SELECT COUNT(*) FROM Payments WHERE oderID = ?", (order_id,),
    ).fetchone()[0]
    def simulate_failure(*args, **kwargs):
        raise RuntimeError("payment database offline")
    monkeypatch.setattr(payment_repository, "insert_payment", simulate_failure)
    with pytest.raises(collect.CollectionError, match="Unable to create"):
        collect.request_remaining_payment(1, order_id, "CASH")
    assert track["rollbacks"] >= 1
    assert raw.execute(
        "SELECT COUNT(*) FROM Payments WHERE oderID = ?", (order_id,),
    ).fetchone()[0] == initial
