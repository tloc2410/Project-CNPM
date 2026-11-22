"""Admin integration tests: shared MySQL-shaped schema, customer and payment routes."""

from datetime import date
from decimal import Decimal

import pytest

from business import booking_service
from test_cart_booking import booking_db, flask_client, _login_session


def _admin(client, raw):
    raw.execute(
        """INSERT INTO Users
           (UserID, fullName, phone, email, passwordHash, role, isLocked)
           VALUES (3, 'Group12 Admin', '0900000000', 'admin@group12.vn',
                   'demo-hash', 'ADMIN', 0)"""
    )
    _login_session(client, user_id=3, full_name="Group12 Admin")
    with client.session_transaction() as sess:
        sess["role"] = "ADMIN"


def _csrf(client):
    with client.session_transaction() as sess:
        return sess["admin_action_csrf"]


def _order(user_id=1, method="E_WALLET"):
    return booking_service.place_order(
        user_id,
        [{"car_id": 1, "pickup_date": "2026-12-12",
          "return_date": "2026-12-14", "selected": True}],
        "PICKUP", method, today=date(2026, 11, 21),
    )


def test_admin_guest_customer_and_forged_session_are_denied(flask_client, booking_db):
    assert "/login" in flask_client.get("/admin").headers["Location"]
    assert "/login" in flask_client.get("/admin/vehicles").headers["Location"]
    _login_session(flask_client, user_id=1)
    assert flask_client.get("/admin/users").status_code == 403
    with flask_client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    assert flask_client.get("/admin/orders").status_code == 403


def test_admin_dashboard_and_reports_use_real_database(flask_client, booking_db):
    raw, _ = booking_db
    _order(method="E_WALLET")
    _admin(flask_client, raw)
    for url in ("/admin", "/admin/dashboard", "/admin/vehicles",
                "/admin/users", "/admin/orders", "/admin/reports"):
        res = flask_client.get(url)
        assert res.status_code == 200, (url, res.get_data(as_text=True)[:500])
    report = flask_client.get("/admin/reports").get_data(as_text=True)
    assert "Recorded Paid" in report
    assert "360.000" in report
    assert "142.500.000" not in report
    vehicles = flask_client.get("/admin/vehicles").get_data(as_text=True)
    assert "Toyota Vios" in vehicles
    assert "DH00123" not in vehicles
    assert "Revenue Over the Last 7 Days" not in vehicles
    assert 'data-price="600000' in vehicles
    assert 'id="fDescription"' in vehicles
    orders = flask_client.get("/admin/orders").get_data(as_text=True)
    assert "Toyota Vios" in orders
    assert "Do Thu Thao" in orders
    assert "1.200.000" in orders


def test_admin_vehicle_and_type_crud_persists_sql(flask_client, booking_db):
    raw, _ = booking_db
    _admin(flask_client, raw)
    assert flask_client.get("/admin/vehicles").status_code == 200
    csrf = _csrf(flask_client)
    no_csrf = flask_client.post("/admin/vehicles/add", data={
        "name": "Test Vehicle", "license_plate": "TEST-9",
        "seats": "4", "type_id": "1", "daily_price": "550000",
        "status": "available",
    })
    assert no_csrf.status_code == 400
    assert raw.execute("SELECT COUNT(*) FROM Cars WHERE code='TEST-9'").fetchone()[0] == 0

    assert flask_client.post("/admin/vehicle-types/add", data={
        "csrf_token": csrf, "name": "Coupe", "description": "Sports car"
    }).status_code == 302
    type_id = raw.execute(
        "SELECT typeId FROM CarTypes WHERE typeName='Coupe'"
    ).fetchone()[0]
    created = flask_client.post("/admin/vehicles/add", data={
        "csrf_token": csrf, "name": "Test Coupe", "license_plate": "COUPE-9",
        "seats": "2", "type_id": str(type_id), "daily_price": "900000",
        "status": "available", "description": "Sport coupe",
    })
    assert created.status_code == 302
    row = raw.execute("SELECT carID, status FROM Cars WHERE code='COUPE-9'").fetchone()
    car_id = row["carID"]
    assert row["status"] == "available"
    modified = flask_client.post(f"/admin/vehicles/{car_id}/edit", data={
        "csrf_token": csrf, "name": "Test Coupe Updated",
        "license_plate": "COUPE-9", "seats": "2",
        "type_id": str(type_id), "daily_price": "950000",
        "status": "available",
    })
    assert modified.status_code == 302
    status = flask_client.post(f"/admin/vehicles/{car_id}/status", data={
        "csrf_token": csrf, "status": "maintenance"
    })
    assert status.status_code == 302
    row = raw.execute("SELECT name, pricePerDay, status, description FROM Cars WHERE carID=?",
                      (car_id,)).fetchone()
    assert row["name"] == "Test Coupe Updated"
    assert row["pricePerDay"] == 950000
    assert row["status"] == "maintenance"
    assert row["description"] == "Sport coupe"
    assert flask_client.post(f"/admin/vehicles/{car_id}/delete",
                             data={"csrf_token": csrf}).status_code == 302
    assert raw.execute("SELECT COUNT(*) FROM Cars WHERE carID=?",
                       (car_id,)).fetchone()[0] == 0
    assert flask_client.post(f"/admin/vehicle-types/{type_id}/delete",
                             data={"csrf_token": csrf}).status_code == 302
    assert raw.execute("SELECT COUNT(*) FROM CarTypes WHERE typeId=?",
                       (type_id,)).fetchone()[0] == 0


def test_admin_users_lock_persists_and_rejects_locked_sessions(flask_client, booking_db):
    raw, _ = booking_db
    _admin(flask_client, raw)
    assert flask_client.get("/admin/users").status_code == 200
    csrf = _csrf(flask_client)
    own = flask_client.post("/admin/users/3/toggle-lock",
                            data={"csrf_token": csrf})
    assert own.status_code == 302
    assert raw.execute("SELECT isLocked FROM Users WHERE UserID=3").fetchone()[0] == 0
    blocked = flask_client.post("/admin/users/1/toggle-lock",
                                data={"csrf_token": csrf})
    assert blocked.status_code == 302
    assert raw.execute("SELECT isLocked FROM Users WHERE UserID=1").fetchone()[0] == 1

    _login_session(flask_client, user_id=1)
    res = flask_client.get("/cart")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]
    _admin_login_without_seed(flask_client)
    assert flask_client.get("/admin/users").status_code == 200
    with flask_client.session_transaction() as sess:
        csrf = sess["admin_action_csrf"]
    assert flask_client.post("/admin/users/1/toggle-lock",
                             data={"csrf_token": csrf}).status_code == 302
    assert raw.execute("SELECT isLocked FROM Users WHERE UserID=1").fetchone()[0] == 0


def _admin_login_without_seed(client):
    _login_session(client, user_id=3, full_name="Group12 Admin")
    with client.session_transaction() as sess:
        sess["role"] = "ADMIN"


def test_admin_order_status_and_refund_is_atomic(flask_client, booking_db):
    raw, _ = booking_db
    order_id = _order(method="E_WALLET")
    _admin(flask_client, raw)
    assert flask_client.get("/admin/orders").status_code == 200
    csrf = _csrf(flask_client)
    invalid = flask_client.post(f"/admin/orders/{order_id}/status", data={
        "csrf_token": csrf, "status": "COMPLETED",
    })
    assert invalid.status_code == 302
    assert "error=" in invalid.headers["Location"]
    assert raw.execute("SELECT status FROM Orders WHERE oderID=?",
                       (order_id,)).fetchone()[0] == "PENDING"
    confirmed = flask_client.post(f"/admin/orders/{order_id}/status", data={
        "csrf_token": csrf, "status": "CONFIRMED",
    })
    assert confirmed.status_code == 302
    assert raw.execute("SELECT status FROM Orders WHERE oderID=?",
                       (order_id,)).fetchone()[0] == "CONFIRMED"
    cancelled = flask_client.post(f"/admin/orders/{order_id}/status", data={
        "csrf_token": csrf, "status": "CANCELLED",
    })
    assert cancelled.status_code == 302
    assert raw.execute("SELECT status FROM Orders WHERE oderID=?",
                       (order_id,)).fetchone()[0] == "CANCELLED"
    assert raw.execute("SELECT paymentStatus FROM Payments WHERE oderID=?",
                       (order_id,)).fetchone()[0] == "Refund Pending"
    retry = flask_client.post(f"/admin/orders/{order_id}/status", data={
        "csrf_token": csrf, "status": "CONFIRMED",
    })
    assert "error=" in retry.headers["Location"]


def test_admin_cash_and_bank_payment_confirmation_integrates_existing_flow(
    flask_client, booking_db
):
    raw, _ = booking_db
    order_id = _order(method="BANK_TRANSFER")
    _admin(flask_client, raw)
    page = flask_client.get("/admin/payments")
    assert page.status_code == 200
    assert b"Bank Transfer" in page.data
    with flask_client.session_transaction() as sess:
        csrf = sess["admin_payment_csrf"]
    payment_id = raw.execute(
        "SELECT paymentID FROM Payments WHERE oderID=?", (order_id,)
    ).fetchone()[0]
    wrong_csrf = flask_client.post(f"/admin/payments/{payment_id}/confirm", data={
        "csrf_token": "invalid", "verified": "yes"
    })
    assert wrong_csrf.status_code == 400
    pending = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID=?", (payment_id,)
    ).fetchone()[0]
    assert pending == "Pending"
    approved = flask_client.post(f"/admin/payments/{payment_id}/confirm", data={
        "csrf_token": csrf, "verified": "yes",
    })
    assert approved.status_code == 302
    assert raw.execute("SELECT paymentStatus FROM Payments WHERE paymentID=?",
                       (payment_id,)).fetchone()[0] == "Paid"
    assert raw.execute("SELECT status FROM Orders WHERE oderID=?",
                       (order_id,)).fetchone()[0] == "CONFIRMED"


def test_admin_cannot_edit_vehicles_or_users_with_spoofed_customer_role(
    flask_client, booking_db
):
    raw, _ = booking_db
    _admin(flask_client, raw)
    flask_client.get("/admin/vehicles")
    csrf = _csrf(flask_client)
    with flask_client.session_transaction() as sess:
        sess["role"] = "CUSTOMER"
    assert flask_client.post("/admin/vehicles/1/delete",
                             data={"csrf_token": csrf}).status_code == 403
    assert flask_client.post("/admin/users/1/toggle-lock",
                             data={"csrf_token": csrf}).status_code == 403
    assert raw.execute("SELECT COUNT(*) FROM Cars WHERE carID=1").fetchone()[0] == 1
    assert raw.execute("SELECT isLocked FROM Users WHERE UserID=1").fetchone()[0] == 0
