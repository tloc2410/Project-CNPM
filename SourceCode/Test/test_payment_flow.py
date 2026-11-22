"""Payment regression tests with SQLite/Flask fixtures; no real money moves."""
import re
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


def _pending_id(raw, order_id):
    return raw.execute(
        """SELECT paymentID FROM Payments
           WHERE oderID = ? AND paymentStatus = 'Pending'
           ORDER BY paymentID DESC LIMIT 1""", (order_id,),
    ).fetchone()[0]




def test_payment_01_bank_deposit_pending_with_reference():
    plan = pay.plan_payment(
        "BANK_TRANSFER", 7, 500000, 150000, transfer_reference="G12TEST7"
    )
    assert plan.amount == Decimal("150000")
    assert plan.status == "Pending"
    assert plan.transaction_code == "G12TEST7"
    assert plan.paid_at is None


def test_payment_02_cash_full_amount_pending_at_pickup():
    plan = pay.plan_payment("CASH", 5, 500000, 150000)
    assert plan.status == "Pending"
    assert plan.amount == Decimal("500000")
    assert plan.paid_at is None


def test_payment_03_vietqr_encodes_deposit_and_reference(monkeypatch):
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "GROUP12 DEMO")
    url = qr.bank_transfer_qr(150000, "G12DEMO123")
    assert url.startswith("https://img.vietqr.io/image/970436-0000000000-compact2.png?")
    params = parse_qs(urlparse(url).query)
    assert params["amount"] == ["150000"]
    assert params["addInfo"] == ["G12DEMO123"]
    assert params["accountName"] == ["GROUP12 DEMO"]


def test_payment_04_momo_page_requires_existing_merchant_qr_file(
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




def test_payment_05_checkout_stages_draft_without_order_or_payment(
    flask_client, booking_db
):
    _checkout(flask_client)
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 0
    assert b"Complete Your Payment" in flask_client.get("/payment").data


def test_payment_06_demo_decline_keeps_cart_and_creates_no_order(
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


def test_payment_07_wallet_confirmation_saves_deposit_and_receipt(
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


@pytest.mark.parametrize("action", ["confirm", "declined", "mystery"])
def test_payment_08_bad_csrf_never_commits_checkout(
    flask_client, booking_db, action
):
    _checkout(flask_client)
    rejected = flask_client.post("/payment", data={
        "payment_csrf": "forged", "payment_action": action,
    })
    assert rejected.status_code == 400
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


def test_payment_09_successful_payment_post_cannot_be_replayed(
    flask_client, booking_db
):
    token = _checkout(flask_client)
    payload = {"payment_csrf": token, "payment_action": "confirm"}
    assert flask_client.post("/payment", data=payload).status_code == 302
    assert flask_client.post("/payment", data=payload).status_code == 302
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 1
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1




def test_payment_10_unverified_bank_deposit_blocks_second_payment(booking_db):
    raw, _ = booking_db
    order_id = _order("BANK_TRANSFER")
    with pytest.raises(collect.CollectionError, match="deposit must be verified"):
        collect.request_remaining_payment(1, order_id, "CASH")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1


@pytest.mark.parametrize("method", ["E_WALLET", "BANK_TRANSFER", "CASH"])
def test_payment_11_remaining_request_is_exact_unpaid_amount(booking_db, method):
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


def test_payment_12_duplicate_remaining_request_is_rejected(booking_db):
    raw, _ = booking_db
    order_id = _order()
    collect.request_remaining_payment(1, order_id, "BANK_TRANSFER")
    with pytest.raises(collect.CollectionError, match="awaiting verification"):
        collect.request_remaining_payment(1, order_id, "CASH")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 2


def test_payment_13_bank_balance_page_shows_qr_of_70_percent(
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




def test_payment_14_session_admin_spoof_fails_database_role_check(
    flask_client, booking_db
):
    _login_session(flask_client)
    with flask_client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    assert flask_client.get("/admin/payments").status_code == 403


def test_payment_15_admin_verification_needs_valid_csrf_and_acknowledgment(
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


def test_payment_16_staff_verified_deposit_confirms_order(booking_db):
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


def test_payment_17_staff_verified_balance_marks_paid_in_full_once(booking_db):
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


def test_payment_18_cancellation_requires_manual_refund_not_fake_refunded(booking_db):
    raw, _ = booking_db
    order_id = _order()
    collect.request_remaining_payment(1, order_id, "BANK_TRANSFER")
    booking.cancel_order(1, order_id)
    rows = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE oderID = ? ORDER BY paymentID",
        (order_id,),
    ).fetchall()
    assert [x[0] for x in rows] == ["Refund Pending", "Cancelled"]




def test_payment_19_failed_initial_payment_insert_rolls_back_everything(
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


def test_payment_20_failed_remaining_insert_leaves_original_deposit_unchanged(
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



def test_demo_bank_deposit_without_admin_unlocks_remaining_payment(
    flask_client, booking_db, monkeypatch
):
    monkeypatch.setenv("DEMO_PAYMENT_MODE", "1")
    token = _checkout(flask_client, "BANK_TRANSFER")
    page = flask_client.get("/payment").get_data(as_text=True)
    assert "DEMO QR" in page
    assert "NOT SCANNABLE" in page
    assert "Bank QR is not configured yet" not in page
    confirm = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert confirm.status_code == 302
    raw, _ = booking_db
    assert raw.execute(
        "SELECT paymentStatus FROM Payments LIMIT 1"
    ).fetchone()[0] == "Pending"
    view = flask_client.get("/orders/1/payment").get_data(as_text=True)
    assert "Simulate Deposit Received" in view
    with flask_client.session_transaction() as sess:
        csrf = sess["demo_payment_csrf"]
    result = flask_client.post("/orders/1/payment/demo", data={
        "csrf_token": csrf, "action": "success",
    })
    assert result.status_code == 302
    order = booking.get_order_payment_details(1, 1)
    assert order["paid_amount"] == 180000
    assert order["balance_due"] == 420000
    assert order["can_pay_remaining"]
    assert order["payment_status"] == "Partially Paid"
    payment = raw.execute(
        "SELECT transactionCode FROM Payments LIMIT 1"
    ).fetchone()[0]
    assert payment.endswith("-DEMO")


def test_demo_remaining_failure_retry_and_paid_in_full(
    flask_client, booking_db, monkeypatch
):
    monkeypatch.setenv("DEMO_PAYMENT_MODE", "1")
    raw, _ = booking_db
    order_id = _order()
    _login_session(flask_client)
    url = f"/orders/{order_id}/pay-remaining"
    assert flask_client.get(url).status_code == 200
    with flask_client.session_transaction() as sess:
        csrf = sess["collection_csrf"]
    request1 = flask_client.post(url, data={
        "csrf_token": csrf, "action": "request",
        "payment_method": "BANK_TRANSFER",
    })
    assert request1.status_code == 302
    page = flask_client.get(url).get_data(as_text=True)
    assert "DEMO QR" in page and "Simulate Failed Payment" in page
    failed = flask_client.post(url, data={
        "csrf_token": csrf, "action": "demo_failed",
    })
    assert failed.status_code == 302
    row = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE transactionCode LIKE 'BAL-%'"
    ).fetchone()
    assert row["paymentStatus"] == "Failed"
    assert booking.get_order_payment_details(1, order_id)["can_pay_remaining"]

    request2 = flask_client.post(url, data={
        "csrf_token": csrf, "action": "request",
        "payment_method": "E_WALLET",
    })
    assert request2.status_code == 302
    completed = flask_client.post(url, data={
        "csrf_token": csrf, "action": "demo_success",
    })
    assert completed.status_code == 302
    assert completed.headers["Location"].endswith(f"/orders/{order_id}/payment")
    order = booking.get_order_payment_details(1, order_id)
    assert order["paid_amount"] == 600000
    assert order["balance_due"] == 0
    assert order["payment_status"] == "Paid in Full"
    assert [p["paymentStatus"] for p in order["payments"]].count("Paid") == 2
    assert [p["paymentStatus"] for p in order["payments"]].count("Failed") == 1
    flask_client.post(url, data={
        "csrf_token": csrf, "action": "demo_success",
    })
    assert booking.get_order_payment_details(1, order_id)["paid_amount"] == 600000


def test_demo_cash_payment_collected_at_pickup(flask_client, booking_db, monkeypatch):
    monkeypatch.setenv("DEMO_PAYMENT_MODE", "1")
    order_id = _order("CASH")
    _login_session(flask_client)
    page = flask_client.get(f"/orders/{order_id}/payment")
    assert b"Simulate Cash Collected at Pickup" in page.data
    with flask_client.session_transaction() as sess:
        csrf = sess["demo_payment_csrf"]
    result = flask_client.post(f"/orders/{order_id}/payment/demo", data={
        "csrf_token": csrf, "action": "success",
    })
    assert result.status_code == 302
    overview = booking.get_order_payment_details(1, order_id)
    assert overview["paid_amount"] == 600000
    assert overview["balance_due"] == 0
    assert overview["payment_status"] == "Paid in Full"


def test_demo_routes_disabled_and_customer_ownership_enforced(
    flask_client, booking_db, monkeypatch
):
    order_id = _order("BANK_TRANSFER")
    _login_session(flask_client, user_id=1)
    flask_client.get(f"/orders/{order_id}/payment")
    with flask_client.session_transaction() as sess:
        csrf = sess["demo_payment_csrf"]
    monkeypatch.setenv("DEMO_PAYMENT_MODE", "0")
    rejected = flask_client.post(f"/orders/{order_id}/payment/demo", data={
        "csrf_token": csrf, "action": "success",
    })
    assert rejected.status_code == 404
    monkeypatch.setenv("DEMO_PAYMENT_MODE", "1")
    forged = flask_client.post(f"/orders/{order_id}/payment/demo", data={
        "csrf_token": "invalid", "action": "success",
    })
    assert forged.status_code == 400
    _login_session(flask_client, user_id=2)
    denied = flask_client.post(f"/orders/{order_id}/payment/demo", data={
        "csrf_token": csrf, "action": "success",
    })
    assert denied.status_code == 404
    raw, _ = booking_db
    assert raw.execute(
        "SELECT paymentStatus FROM Payments LIMIT 1"
    ).fetchone()[0] == "Pending"
