"""Automated test suite for module Rental Cart & Booking (Do Thu Thao).

Executes real SQL from SourceCode/data/booking_repository.py against an
in-memory transactional SQLite database mirroring the exact schema of
Database/group12_car_rental.sql (Users, CarTypes, Cars, Orders, Oderitem).

Covers:
  1. Cart management (add, duplicate check, remove, select/unselect, bulk remove)
  2. Date validation (empty, past, return <= pickup, > 60 days)
  3. Automatic fee calculation (line total, subtotal, PICKUP vs DELIVERY,
     free delivery >= 2,000,000 VND, 30% deposit)
  4. Anti-overlap booking check (exact, partial, boundary, non-overlap, cancelled)
  5. Transactional place_order + mid-transaction failure ROLLBACK verification
  6. Transactional cancel_order + ownership/status guards + ROLLBACK verification
  7. End-to-end Flask Blueprint route tests (/cart, /api/cart/*, /checkout, /orders)
"""

import os
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

# Ensure run.py can be imported cleanly even without a local .env file
os.environ.setdefault("SECRET_KEY", "test-secret-key-booking-suite")

from business import booking_service as svc
from data import booking_repository as repo
from data import database


# ---------------------------------------------------------------------------
# Transactional SQLite adapter mimicking mysql.connector (Real SQL + ROLLBACK)
# ---------------------------------------------------------------------------
class _SQLiteMySQLCursor:
    def __init__(self, conn, dictionary=False):
        self._conn = conn
        self._cur = conn.cursor()
        self._dictionary = dictionary
        self.lastrowid = None
        self.rowcount = 0

    @staticmethod
    def _adapt_sql(sql):
        # Convert MySQL %s placeholders to SQLite ? and strip FOR UPDATE
        adapted = sql.replace("%s", "?")
        adapted = re.sub(r"\bFOR\s+UPDATE\b", "", adapted, flags=re.IGNORECASE)
        return adapted

    @staticmethod
    def _adapt_params(params):
        if not params:
            return ()
        out = []
        for p in params:
            if isinstance(p, Decimal):
                out.append(float(p))
            elif isinstance(p, datetime):
                out.append(p.strftime("%Y-%m-%d %H:%M:%S"))
            elif isinstance(p, date):
                out.append(p.isoformat())
            else:
                out.append(p)
        return tuple(out)

    def execute(self, sql, params=None):
        adapted_sql = self._adapt_sql(sql)
        adapted_params = self._adapt_params(params)
        self._cur.execute(adapted_sql, adapted_params)
        self.lastrowid = self._cur.lastrowid
        self.rowcount = self._cur.rowcount

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row) if self._dictionary else tuple(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        if self._dictionary:
            return [dict(r) for r in rows]
        return [tuple(r) for r in rows]

    def close(self):
        self._cur.close()


class _SQLiteMySQLConnection:
    """Wraps a shared sqlite3 connection while tracking commit/rollback calls."""

    def __init__(self, raw_conn, tracker):
        self._raw = raw_conn
        self._tracker = tracker

    def cursor(self, dictionary=False):
        return _SQLiteMySQLCursor(self._raw, dictionary=dictionary)

    def start_transaction(self):
        self._tracker["started"] += 1
        if not self._raw.in_transaction:
            self._raw.execute("BEGIN")

    def commit(self):
        self._tracker["commits"] += 1
        self._raw.commit()

    def rollback(self):
        self._tracker["rollbacks"] += 1
        self._raw.rollback()

    def close(self):
        # Keep the shared in-memory DB alive for the duration of the test case.
        pass


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE Users (
    UserID INTEGER PRIMARY KEY AUTOINCREMENT,
    fullName TEXT NOT NULL,
    dateOfBirth TEXT,
    gender TEXT,
    address TEXT,
    phone TEXT,
    email TEXT NOT NULL UNIQUE,
    passwordHash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'CUSTOMER',
    isLocked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE CarTypes (
    typeId INTEGER PRIMARY KEY AUTOINCREMENT,
    typeName TEXT NOT NULL,
    description TEXT
);

CREATE TABLE Cars (
    carID INTEGER PRIMARY KEY AUTOINCREMENT,
    TypeID INTEGER NOT NULL,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    pictures TEXT,
    description TEXT,
    numberOfSeats INTEGER,
    pricePerDay REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    numberOfViews INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (TypeID) REFERENCES CarTypes(typeId)
);

CREATE TABLE Orders (
    oderID INTEGER PRIMARY KEY AUTOINCREMENT,
    useID INTEGER NOT NULL,
    orderTime TEXT,
    status TEXT,
    receivingMethod TEXT,
    deliveryFee REAL,
    deposit REAL,
    totalPrice REAL,
    paymentMethod TEXT,
    FOREIGN KEY (useID) REFERENCES Users(UserID)
);

CREATE TABLE Payments (
    paymentID INTEGER PRIMARY KEY AUTOINCREMENT,
    oderID INTEGER NOT NULL,
    amount REAL NOT NULL,
    paymentMethod TEXT,
    paymentStatus TEXT,
    transactionCode TEXT,
    paidAt TEXT,
    FOREIGN KEY (oderID) REFERENCES Orders(oderID)
);

CREATE TABLE Oderitem (
    OderitemID INTEGER PRIMARY KEY AUTOINCREMENT,
    OderID INTEGER NOT NULL,
    CarID INTEGER NOT NULL,
    unitPrice REAL,
    rentalDays INTEGER,
    pickupDate TEXT,
    returnDate TEXT,
    FOREIGN KEY (OderID) REFERENCES Orders(oderID),
    FOREIGN KEY (CarID) REFERENCES Cars(carID)
);
"""


@pytest.fixture
def booking_db(monkeypatch):
    raw = sqlite3.connect(":memory:", isolation_level=None)
    raw.row_factory = sqlite3.Row
    raw.executescript(SCHEMA_SQL)

    # Seed users, car types, and cars matching Figma + group schema
    raw.executemany(
        "INSERT INTO Users (UserID, fullName, phone, email, passwordHash, role) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "Do Thu Thao", "0912345678", "thao@group12.vn", "hash1", "CUSTOMER"),
            (2, "Nguyen Van B", "0987654321", "user2@group12.vn", "hash2", "CUSTOMER"),
        ],
    )
    raw.executemany(
        "INSERT INTO CarTypes (typeId, typeName, description) VALUES (?, ?, ?)",
        [
            (1, "Sedan 4 cho", "Sedan"),
            (2, "MPV 7 cho", "MPV"),
        ],
    )
    raw.executemany(
        """
        INSERT INTO Cars (carID, TypeID, code, name, pictures, description, numberOfSeats, pricePerDay, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 1, "VIOS-01", "Toyota Vios", "toyotavios2023.webp", "Automatic · Petrol", 4, 600000.0, "available"),
            (2, 1, "CITY-02", "Honda City", "hondacity2022.webp", "Automatic · Petrol", 4, 650000.0, "available"),
            (3, 2, "CARNIVAL-03", "Kia Carnival", "/static/images/booking/car_carnival.svg", "Automatic · Diesel", 7, 1400000.0, "available"),
            (4, 1, "MAINT-04", "Mazda 3", "", "Under maintenance", 4, 700000.0, "maintenance"),
        ],
    )

    tracker = {"started": 0, "commits": 0, "rollbacks": 0}

    def fake_get_conn():
        return _SQLiteMySQLConnection(raw, tracker)

    monkeypatch.setattr(database, "get_db_connection", fake_get_conn)
    yield raw, tracker
    raw.close()


# ===========================================================================
# 1. Cart Pure Operations Tests
# ===========================================================================
def test_cart_add_duplicate_and_remove():
    cart = []
    cart, added, msg = svc.add_to_cart(cart, 1, "2026-12-01", "2026-12-03")
    assert added is True
    assert len(cart) == 1
    assert cart[0]["car_id"] == 1
    assert cart[0]["selected"] is True

    # Adding same car again must be rejected
    cart, added_again, msg2 = svc.add_to_cart(cart, 1)
    assert added_again is False
    assert len(cart) == 1
    assert "đã có" in msg2.lower()

    # Add second car then remove first
    cart, added2, _ = svc.add_to_cart(cart, 2, "2026-12-05", "2026-12-07")
    assert added2 is True
    assert len(cart) == 2

    cart, removed = svc.remove_from_cart(cart, 1)
    assert removed is True
    assert [i["car_id"] for i in cart] == [2]


def test_cart_selection_and_remove_selected():
    cart = []
    cart, _, _ = svc.add_to_cart(cart, 1, selected=True)
    cart, _, _ = svc.add_to_cart(cart, 2, selected=True)

    cart = svc.set_item_selected(cart, 1, False)
    assert [i["car_id"] for i in svc.get_selected_cart_items(cart)] == [2]

    cart, removed_count = svc.remove_selected_from_cart(cart)
    assert removed_count == 1
    assert [i["car_id"] for i in cart] == [1]

    cart = svc.set_all_selected(cart, True)
    assert all(i["selected"] for i in cart)


# ===========================================================================
# 2. Date Validation & Automatic Pricing Tests
# ===========================================================================
def test_validate_dates_invalid_and_valid():
    today = date(2026, 11, 21)

    ok, msg, days = svc.validate_dates("", "2026-11-25", today=today)
    assert ok is False and days == 0

    ok, msg, days = svc.validate_dates("2026-11-20", "2026-11-25", today=today)
    assert ok is False and "quá khứ" in msg.lower()

    ok, msg, days = svc.validate_dates("2026-11-25", "2026-11-25", today=today)
    assert ok is False and "sau ngày nhận" in msg.lower()

    ok, msg, days = svc.validate_dates("2026-11-25", "2026-11-22", today=today)
    assert ok is False and "sau ngày nhận" in msg.lower()

    ok, msg, days = svc.validate_dates("2026-11-25", "2027-02-25", today=today)
    assert ok is False and "60" in msg

    ok, msg, days = svc.validate_dates("2026-11-25", "2026-11-28", today=today)
    assert ok is True and msg == "" and days == 3


def test_automatic_fee_calculation_and_free_delivery():
    # 1 car x 2 days = 1,200,000 VND
    line1 = svc.calculate_line_total(Decimal("600000"), 2)
    assert line1 == Decimal("1200000")

    # PICKUP: delivery fee is always 0
    t_pickup = svc.calculate_totals([line1], receiving_method="PICKUP")
    assert t_pickup["subtotal"] == Decimal("1200000")
    assert t_pickup["delivery_fee"] == Decimal("0")
    assert t_pickup["total"] == Decimal("1200000")
    assert t_pickup["deposit"] == Decimal("360000")

    # DELIVERY under 2,000,000 VND -> 100,000 VND fee
    t_del = svc.calculate_totals([line1], receiving_method="DELIVERY")
    assert t_del["delivery_fee"] == Decimal("100000")
    assert t_del["total"] == Decimal("1300000")
    assert t_del["deposit"] == Decimal("390000")

    # DELIVERY >= 2,000,000 VND -> Free delivery!
    line2 = svc.calculate_line_total(Decimal("1400000"), 2)  # 2,800,000
    t_free_del = svc.calculate_totals([line2], receiving_method="DELIVERY")
    assert t_free_del["delivery_fee"] == Decimal("0")
    assert t_free_del["total"] == Decimal("2800000")
    assert t_free_del["deposit"] == Decimal("840000")


# ===========================================================================
# 3. Overlap Check Tests (Real SQL)
# ===========================================================================
def test_overlap_detection_blocks_conflicts_and_allows_free_ranges(booking_db):
    today = date(2026, 11, 21)

    # First customer books Toyota Vios (carID=1) for 2026-12-10 -> 2026-12-15
    cart1 = [{"car_id": 1, "pickup_date": "2026-12-10", "return_date": "2026-12-15", "selected": True}]
    order_id = svc.place_order(1, cart1, "PICKUP", "E_WALLET", today=today)
    assert order_id > 0

    # Overlapping cases MUST be blocked
    overlapping_ranges = [
        ("2026-12-10", "2026-12-15"),  # exact same range
        ("2026-12-08", "2026-12-12"),  # overlaps start
        ("2026-12-13", "2026-12-18"),  # overlaps end
        ("2026-12-11", "2026-12-14"),  # strictly inside
        ("2026-12-09", "2026-12-16"),  # strictly encloses
        ("2026-12-15", "2026-12-17"),  # touches boundary returnDate
    ]
    for p, r in overlapping_ranges:
        cart_conflict = [{"car_id": 1, "pickup_date": p, "return_date": r, "selected": True}]
        summary = svc.build_cart_summary(cart_conflict, today=today)
        assert summary["is_valid"] is False
        assert summary["items"][0]["overlap_conflict"] is True
        with pytest.raises(svc.BookingError, match="trùng lịch"):
            svc.place_order(2, cart_conflict, "PICKUP", "CASH", today=today)

    # Non-overlapping range MUST succeed
    cart_ok = [{"car_id": 1, "pickup_date": "2026-12-16", "return_date": "2026-12-19", "selected": True}]
    order_id_2 = svc.place_order(2, cart_ok, "PICKUP", "CASH", today=today)
    assert order_id_2 > order_id


# ===========================================================================
# 4. Transaction & ROLLBACK Verification Tests
# ===========================================================================
def test_place_order_success_persists_order_and_items(booking_db):
    raw, tracker = booking_db
    today = date(2026, 11, 21)

    cart = [
        {"car_id": 1, "pickup_date": "2026-12-01", "return_date": "2026-12-03", "selected": True},  # 2 * 600k = 1.2M
        {"car_id": 2, "pickup_date": "2026-12-01", "return_date": "2026-12-02", "selected": True},  # 1 * 650k = 650k
    ]
    order_id = svc.place_order(1, cart, receiving_method="DELIVERY", payment_method="BANK_TRANSFER", today=today)

    assert order_id == 1
    assert tracker["commits"] == 1
    assert tracker["rollbacks"] == 0

    order_row = dict(raw.execute("SELECT * FROM Orders WHERE oderID = ?", (order_id,)).fetchone())
    assert order_row["useID"] == 1
    assert order_row["status"] == "PENDING"
    assert order_row["receivingMethod"] == "DELIVERY"
    assert order_row["paymentMethod"] == "BANK_TRANSFER"
    # 1,850,000 + 100,000 delivery = 1,950,000
    assert order_row["deliveryFee"] == 100000.0
    assert order_row["totalPrice"] == 1950000.0
    assert order_row["deposit"] == 585000.0

    items = [dict(r) for r in raw.execute("SELECT * FROM Oderitem WHERE OderID = ? ORDER BY CarID", (order_id,)).fetchall()]
    assert len(items) == 2
    assert items[0]["CarID"] == 1 and items[0]["rentalDays"] == 2 and items[0]["unitPrice"] == 600000.0
    assert items[1]["CarID"] == 2 and items[1]["rentalDays"] == 1 and items[1]["unitPrice"] == 650000.0


def test_place_order_mid_transaction_error_triggers_full_rollback(booking_db, monkeypatch):
    """Simulate a DB crash while inserting the 2nd Oderitem AFTER Orders and
    the 1st Oderitem were inserted. Verify ROLLBACK leaves ZERO orphan rows!"""
    raw, tracker = booking_db
    today = date(2026, 11, 21)

    real_insert_item = repo.insert_order_item
    call_count = {"n": 0}

    def flaky_insert_item(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("Simulated mid-transaction MySQL crash!")
        return real_insert_item(*args, **kwargs)

    monkeypatch.setattr(repo, "insert_order_item", flaky_insert_item)

    cart = [
        {"car_id": 1, "pickup_date": "2026-12-01", "return_date": "2026-12-03", "selected": True},
        {"car_id": 2, "pickup_date": "2026-12-01", "return_date": "2026-12-04", "selected": True},
    ]

    with pytest.raises(svc.BookingError, match="ROLLBACK"):
        svc.place_order(1, cart, receiving_method="PICKUP", payment_method="E_WALLET", today=today)

    assert tracker["commits"] == 0
    assert tracker["rollbacks"] == 1
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM Oderitem").fetchone()[0] == 0


def test_place_order_unavailable_car_rolls_back(booking_db):
    raw, tracker = booking_db
    today = date(2026, 11, 21)

    cart = [{"car_id": 4, "pickup_date": "2026-12-01", "return_date": "2026-12-03", "selected": True}]
    with pytest.raises(svc.BookingError, match="không ở trạng thái"):
        svc.place_order(1, cart, today=today)

    assert tracker["rollbacks"] == 1
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


# ===========================================================================
# 5. Cancel Order & Calendar Release Tests
# ===========================================================================
def test_cancel_order_frees_calendar_and_enforces_ownership(booking_db):
    raw, tracker = booking_db
    today = date(2026, 11, 21)

    cart = [{"car_id": 1, "pickup_date": "2026-12-20", "return_date": "2026-12-23", "selected": True}]
    order_id = svc.place_order(1, cart, today=today)

    # Another user CANNOT cancel user 1's order
    with pytest.raises(svc.BookingError, match="Không tìm thấy"):
        svc.cancel_order(2, order_id)

    # User 1 cancels own order -> succeeds
    assert svc.cancel_order(1, order_id) is True
    status = raw.execute("SELECT status FROM Orders WHERE oderID = ?", (order_id,)).fetchone()[0]
    assert status == "CANCELLED"

    # Cancelling again is rejected
    with pytest.raises(svc.BookingError, match="không thể hủy"):
        svc.cancel_order(1, order_id)

    # Same car and exact same dates can now be booked by user 2!
    order_id_2 = svc.place_order(2, cart, today=today)
    assert order_id_2 > order_id


def test_cancel_order_db_error_rolls_back(booking_db, monkeypatch):
    raw, tracker = booking_db
    today = date(2026, 11, 21)

    cart = [{"car_id": 1, "pickup_date": "2026-12-20", "return_date": "2026-12-22", "selected": True}]
    order_id = svc.place_order(1, cart, today=today)

    def broken_update(*args, **kwargs):
        raise RuntimeError("Simulated update failure")

    monkeypatch.setattr(repo, "update_order_status", broken_update)

    with pytest.raises(svc.BookingError, match="Hủy đơn thất bại"):
        svc.cancel_order(1, order_id)

    assert tracker["rollbacks"] >= 1
    status = raw.execute("SELECT status FROM Orders WHERE oderID = ?", (order_id,)).fetchone()[0]
    assert status == "PENDING"


# ===========================================================================
# 6. Flask Blueprint End-to-End Integration Tests
# ===========================================================================
@pytest.fixture
def flask_client(booking_db):
    import run as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


def _login_session(client, user_id=1, full_name="Do Thu Thao"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["full_name"] = full_name
        sess["role"] = "CUSTOMER"


def test_routes_require_login(flask_client):
    res = flask_client.get("/cart")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    api_res = flask_client.post("/api/cart/dates", json={"car_id": 1})
    assert api_res.status_code == 401
    assert api_res.get_json()["ok"] is False


def test_full_web_booking_flow_cart_to_checkout_to_cancel(flask_client, booking_db):
    raw, _ = booking_db
    _login_session(flask_client, user_id=1, full_name="Do Thu Thao")

    # 1. Open cart page
    res = flask_client.get("/cart")
    assert res.status_code == 200
    assert b"Your Cart" in res.data
    assert b"Toyota Vios" in res.data

    # 2. Add Toyota Vios (car 1) and Honda City (car 2)
    res = flask_client.post(
        "/cart/add/1",
        data={"pickup_date": "2026-12-10", "return_date": "2026-12-12"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Toyota Vios" in res.data

    flask_client.post(
        "/cart/add/2",
        data={"pickup_date": "2026-12-10", "return_date": "2026-12-11"},
    )

    # 3. Unselect car 2 via API -> summary should only reflect car 1 (2 days * 600k = 1,200,000)
    sel_res = flask_client.post("/api/cart/select", json={"car_id": 2, "selected": False})
    sel_data = sel_res.get_json()
    assert sel_data["ok"] is True
    assert sel_data["selected_count"] == 1
    assert sel_data["subtotal"] == 1200000
    assert sel_data["is_valid"] is True

    # 4. Update car 1 dates via API (3 days -> 1,800,000)
    date_res = flask_client.post(
        "/api/cart/dates",
        json={"car_id": 1, "pickup_date": "2026-12-10", "return_date": "2026-12-13"},
    )
    date_data = date_res.get_json()
    assert date_data["subtotal"] == 1800000
    assert date_data["is_valid"] is True

    # 5. Open Checkout page
    co_get = flask_client.get("/checkout")
    assert co_get.status_code == 200
    assert b"Rental Information" in co_get.data
    assert b"Payment Method" in co_get.data
    assert b"Proceed to Payment" in co_get.data

    # 6. Submit Checkout without agreeing to terms -> blocked with flash
    co_no_terms = flask_client.post(
        "/checkout",
        data={
            "pickup_date": "2026-12-10",
            "return_date": "2026-12-13",
            "receiving_method": "PICKUP",
            "payment_method": "E_WALLET",
        },
        follow_redirects=True,
    )
    assert "Điều khoản".encode("utf-8") in co_no_terms.data

    # 7. Checkout stages an unpaid draft. The separate Payment step creates the order.
    co_ok = flask_client.post(
        "/checkout",
        data={
            "pickup_date": "2026-12-10",
            "return_date": "2026-12-13",
            "pickup_location": "Tan Son Nhat Airport",
            "return_location": "Tan Son Nhat Airport",
            "receiving_method": "PICKUP",
            "payment_method": "E_WALLET",
            "agree_terms": "on",
        },
        follow_redirects=True,
    )
    assert co_ok.status_code == 200
    assert b"Complete Your Payment" in co_ok.data
    assert b"Toyota Vios" in co_ok.data
    with flask_client.session_transaction() as sess:
        assert len(sess["rental_cart"]) == 2
        assert sess.get("pending_payment")
    assert flask_client.get("/orders").status_code == 200
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0

    with flask_client.session_transaction() as sess:
        csrf = sess["pending_payment"]["csrf"]
    complete = flask_client.post("/payment", data={
        "payment_csrf": csrf, "payment_action": "confirm",
    }, follow_redirects=True)
    assert complete.status_code == 200
    assert b"Booking #1" in complete.data

    # Car 2 (unselected) should still remain in cart; car 1 removed
    with flask_client.session_transaction() as sess:
        remaining_ids = [i["car_id"] for i in sess.get("rental_cart", [])]
        assert remaining_ids == [2]

    # 8. Cancel order #1 via POST /orders/1/cancel
    cancel_res = flask_client.post("/orders/1/cancel", follow_redirects=True)
    assert cancel_res.status_code == 200
    assert "Đã hủy đơn hàng #1".encode("utf-8") in cancel_res.data


def test_car_image_url_resolution(flask_client):
    """Verify bare .webp filenames from sample_data_vehicles.sql resolve to /static/images/cars/..."""
    from presentation.booking_routes import car_img_url
    import run as app_module

    with app_module.app.test_request_context():
        assert car_img_url("toyotavios2023.webp") == "/static/images/cars/toyotavios2023.webp"
        assert car_img_url("hondacity2022.webp, interior.webp") == "/static/images/cars/hondacity2022.webp"
        assert car_img_url("/static/images/booking/car_vios.svg") == "/static/images/cars/toyotavios2023.webp"
        assert car_img_url("/static/images/booking/car_city.svg") == "/static/images/cars/hondacity2022.webp"
        assert car_img_url("/static/images/booking/car_vf5.svg") == "https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960"
        assert car_img_url("/static/images/booking/car_vf3.svg") == "/static/images/cars/vinfast_vf3.jpg"
        assert car_img_url("/static/images/booking/car_carnival.svg") == "/static/images/cars/kia_carnival.jpg"
        assert car_img_url("https://example.com/car.jpg") == "https://example.com/car.jpg"
        assert car_img_url("") == "/static/images/cars/car-placeholder.svg"

    _login_session(flask_client, user_id=1, full_name="Do Thu Thao")
    res = flask_client.get("/cart")
    assert res.status_code == 200
    assert b"/static/images/cars/toyotavios2023.webp" in res.data
    assert b"/static/images/cars/hondacity2022.webp" in res.data




def test_booking_available_cards_render_correct_vehicle_photos(flask_client, booking_db):
    """Booking cart should not show demo illustrations for Vios, City or VF 5."""
    raw, _ = booking_db
    raw.execute("UPDATE Cars SET pictures = ? WHERE carID = 1",
                ("/static/images/booking/car_vios.svg",))
    raw.execute("UPDATE Cars SET pictures = ? WHERE carID = 2",
                ("/static/images/booking/car_city.svg",))
    raw.execute(
        """INSERT INTO Cars
           (carID, TypeID, code, name, pictures, numberOfSeats,
            pricePerDay, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (5, 1, "BOOK-VF5-03", "VinFast VF 5",
         "/static/images/booking/car_vf5.svg", 4, 700000, "available")
    )
    _login_session(flask_client)
    body = flask_client.get("/cart").get_data(as_text=True)
    assert 'src="/static/images/cars/toyotavios2023.webp"' in body
    assert 'src="/static/images/cars/hondacity2022.webp"' in body
    assert 'src="https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960"' in body

def test_ajax_add_keeps_page_and_syncs_cart_count_on_vehicle_pages(flask_client):
    """AJAX adds and duplicate requests share one session cart across pages."""
    from unittest.mock import patch
    from business import vehicle_service

    _login_session(flask_client)
    payload = {"pickup_date": "2026-12-15", "return_date": "2026-12-17"}
    first = flask_client.post("/cart/add/1", json=payload)
    assert first.status_code == 200
    data = first.get_json()
    assert data["ok"] is True
    assert data["added"] is True
    assert data["total_count"] == 1

    duplicate = flask_client.post("/cart/add/1", json=payload)
    assert duplicate.status_code == 200
    again = duplicate.get_json()
    assert again["added"] is False
    assert again["total_count"] == 1

    sample_car = {
        "carID": 1, "TypeID": 1, "code": "SEDAN-01",
        "name": "Toyota Vios 2023", "pictures": "toyotavios2023.webp",
        "description": "Test car", "numberOfSeats": 5,
        "pricePerDay": 850000.0, "status": "available",
        "numberOfViews": 10, "typeName": "Sedan", "rentalCount": 0,
    }
    filters = vehicle_service.normalize_filters({})
    with patch.object(vehicle_service, "list_vehicles",
                      return_value=([sample_car], 1, 1, filters)), \
         patch.object(vehicle_service, "list_car_types", return_value=[]), \
         patch.object(vehicle_service, "get_vehicle",
                      return_value=dict(sample_car)):
        for url in ("/", "/cars", "/cars/1"):
            response = flask_client.get(url)
            assert response.status_code == 200
            assert b'id="g12-global-cart-count"' in response.data
            assert b'Your cart (1 vehicles)' in response.data

        detail = flask_client.get("/cars/1").get_data(as_text=True)
        assert 'data-ajax-add-to-cart' in detail
        assert 'data-login-url="/login"' in detail


def test_checkout_custom_pickup_and_return_options(flask_client):
    """Pickup is free text; return can only be pickup address or showroom."""
    _login_session(flask_client)
    flask_client.post("/cart/add/1", data={
        "pickup_date": "2026-12-10", "return_date": "2026-12-12"
    })
    res = flask_client.get("/checkout")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert 'id="co-pickup-location"' in body
    assert 'name="pickup_location"' in body
    assert 'type="text"' in body
    assert 'id="co-return-choice"' in body
    assert 'value="SAME_AS_PICKUP"' in body
    assert 'value="SHOWROOM"' in body
    assert 'data-showroom-location="Group 12 Showroom - District 1"' in body

    address = "123 Nguyen Hue, Phuong Sai Gon, TP HCM"
    response = flask_client.post("/checkout", data={
        "pickup_location": address, "return_choice": "SAME_AS_PICKUP",
        "return_location": "Attacker-controlled value", "payment_method": "CASH", "receiving_method": "DELIVERY",
        # No terms: do not create an order, but save valid locations to the cart.
    })
    assert response.status_code == 302
    with flask_client.session_transaction() as sess:
        assert sess["rental_cart"][0]["pickup_location"] == address
        assert sess["rental_cart"][0]["return_location"] == address

    response = flask_client.post("/checkout", data={
        "pickup_location": address, "return_choice": "SHOWROOM",
        "return_location": "Ignored", "payment_method": "CASH", "receiving_method": "DELIVERY",
    })
    assert response.status_code == 302
    with flask_client.session_transaction() as sess:
        assert sess["rental_cart"][0]["pickup_location"] == address
        assert sess["rental_cart"][0]["return_location"] == "Group 12 Showroom - District 1"


def test_checkout_rejects_blank_pickup_and_invalid_return_option(flask_client):
    """Server rejects bypassing required pickup and tampering with return choice."""
    _login_session(flask_client)
    flask_client.post("/cart/add/1", data={
        "pickup_date": "2026-12-10", "return_date": "2026-12-12"
    })
    blank = flask_client.post("/checkout", data={
        "pickup_location": " ", "return_choice": "SAME_AS_PICKUP",
        "agree_terms": "on", "payment_method": "CASH",
        "receiving_method": "DELIVERY",
    }, follow_redirects=True)
    assert "Vui lòng nhập địa chỉ giao xe tận nơi.".encode("utf-8") in blank.data

    invalid = flask_client.post("/checkout", data={
        "pickup_location": "123 Nguyen Hue, TP HCM",
        "return_choice": "UNTRUSTED_ADDRESS",
        "return_location": "Unknown location",
        "agree_terms": "on", "payment_method": "CASH",
        "receiving_method": "DELIVERY",
    }, follow_redirects=True)
    assert "Vui lòng chọn địa điểm trả xe hợp lệ.".encode("utf-8") in invalid.data


def test_book_now_never_adds_to_cart_and_only_orders_one_vehicle(flask_client, booking_db):
    """Direct checkout leaves an existing multi-selected cart unchanged."""
    raw, _ = booking_db
    _login_session(flask_client)
    for car_id in (1, 2):
        res = flask_client.post(f"/cart/add/{car_id}", data={
            "pickup_date": "2026-12-15", "return_date": "2026-12-17",
        })
        assert res.status_code == 302
    with flask_client.session_transaction() as sess:
        original_cart = [dict(i) for i in sess["rental_cart"]]

    from pathlib import Path
    template = (Path(__file__).resolve().parents[1] /
                "presentation" / "templates" / "car_detail.html").read_text(encoding="utf-8")
    assert "url_for('booking.book_now', car_id=car.carID)" in template

    instant = flask_client.post("/book-now/2", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    assert instant.status_code == 302
    assert "/checkout?mode=now" in instant.headers["Location"]
    with flask_client.session_transaction() as sess:
        assert sess["rental_cart"] == original_cart
        assert sess["direct_booking"]["car_id"] == 2

    page = flask_client.get("/checkout?mode=now")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Honda City" in html
    assert "Toyota Vios" not in html
    assert 'data-checkout-mode="now"' in html
    assert 'action="/checkout?mode=now"' in html

    placed = flask_client.post("/checkout?mode=now", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
        "pickup_location": "123 Nguyen Hue, TP HCM",
        "return_choice": "SAME_AS_PICKUP",
        "receiving_method": "PICKUP",
        "payment_method": "CASH",
        "agree_terms": "on",
    })
    assert placed.status_code == 302
    assert placed.headers["Location"].endswith("/payment")
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0
    with flask_client.session_transaction() as sess:
        assert sess["direct_booking"]["car_id"] == 2
        csrf = sess["pending_payment"]["csrf"]
    approved = flask_client.post("/payment", data={
        "payment_csrf": csrf, "payment_action": "confirm",
    })
    assert approved.status_code == 302
    assert approved.headers["Location"].endswith("/orders/1/payment")
    assert [row[0] for row in raw.execute("SELECT CarID FROM Oderitem")] == [2]
    with flask_client.session_transaction() as sess:
        assert sess["rental_cart"] == original_cart
        assert "direct_booking" not in sess


def test_book_now_without_cart_and_api_changes_only_direct_item(flask_client, booking_db):
    """Instant booking works without a cart; date/price AJAX is independent."""
    _login_session(flask_client)
    res = flask_client.post("/book-now/1", data={
        "pickup_date": "2026-12-14", "return_date": "2026-12-16",
    })
    assert res.status_code == 302
    with flask_client.session_transaction() as sess:
        assert not sess.get("rental_cart")
        assert sess["direct_booking"]["car_id"] == 1

    response = flask_client.post("/api/book-now/dates", json={
        "pickup_date": "2026-12-15",
        "return_date": "2026-12-18",
        "pickup_location": "99 Le Loi, TP HCM",
        "return_location": "99 Le Loi, TP HCM",
        "receiving_method": "DELIVERY",
    })
    assert response.status_code == 200
    result = response.get_json()
    assert result["selected_count"] == 1
    assert result["total_count"] == 1
    assert result["items"][0]["rental_days"] == 3
    with flask_client.session_transaction() as sess:
        assert not sess.get("rental_cart")
        assert sess["direct_booking"]["pickup_date"] == "2026-12-15"
        assert sess["direct_booking"]["pickup_location"] == "99 Le Loi, TP HCM"

    fees = flask_client.post("/api/book-now/summary", json={"receiving_method": "DELIVERY"})
    assert fees.status_code == 200
    assert fees.get_json()["selected_count"] == 1
    cart = flask_client.get("/cart")
    assert cart.status_code == 200
    assert 'id="cart-title-count">0</span>' in cart.get_data(as_text=True)
    assert flask_client.get("/checkout?mode=now").status_code == 200


def test_normal_cart_checkout_ignores_active_instant_booking(flask_client, booking_db):
    """Cart checkout still checks out all selected items as before."""
    _login_session(flask_client)
    for car_id in (1, 2):
        flask_client.post(f"/cart/add/{car_id}", data={
            "pickup_date": "2026-12-15", "return_date": "2026-12-17",
        })
    flask_client.post("/book-now/2", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    page = flask_client.get("/checkout")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Toyota Vios" in html and "Honda City" in html
    assert 'data-checkout-mode="cart"' in html
    assert 'action="/checkout"' in html
    with flask_client.session_transaction() as sess:
        assert [i["car_id"] for i in sess["rental_cart"] if i["selected"]] == [1, 2]


def test_direct_booking_requires_login_and_valid_car(flask_client):
    no_auth = flask_client.post("/book-now/1")
    assert no_auth.status_code == 302
    assert "/login" in no_auth.headers["Location"]
    _login_session(flask_client)
    unavailable = flask_client.post("/book-now/4")
    assert unavailable.status_code == 302
    assert unavailable.headers["Location"].endswith("/cars")
    with flask_client.session_transaction() as sess:
        assert not sess.get("rental_cart")
        assert not sess.get("direct_booking")
    assert flask_client.post("/api/book-now/dates", json={}).status_code == 400
    assert flask_client.post("/api/book-now/summary", json={}).status_code == 400


def test_legacy_book_now_flag_does_not_reselect_cart(flask_client):
    """The old cart/add book_now flag cannot change cart checkboxes."""
    _login_session(flask_client)
    flask_client.post("/cart/add/1", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    flask_client.post("/cart/add/2", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    flask_client.post("/api/cart/select", json={"car_id": 2, "selected": False})
    flask_client.post("/cart/add/2", data={"book_now": "1"})
    with flask_client.session_transaction() as sess:
        assert [i["car_id"] for i in sess["rental_cart"] if i["selected"]] == [1]
    assert flask_client.post("/api/cart/select", json={"select_all": True}).get_json()["selected_count"] == 2


def test_cart_and_checkout_do_not_display_default_pickup_location(flask_client):
    """Cart cards and checkout summary hide default address, while pickup input remains."""
    _login_session(flask_client)
    resp = flask_client.post("/cart/add/1", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    assert resp.status_code == 302

    cart = flask_client.get("/cart")
    assert cart.status_code == 200
    cart_html = cart.get_data(as_text=True)
    assert "Tan Son Nhat Airport" not in cart_html
    assert "cart-car-location" not in cart_html

    checkout = flask_client.get("/checkout")
    assert checkout.status_code == 200
    html = checkout.get_data(as_text=True)
    assert "Tan Son Nhat Airport" not in html
    assert "data-co-loc=" not in html
    assert 'id="co-pickup-location"' in html
    assert 'name="pickup_location"' in html
    assert 'id="co-return-choice"' in html


def test_showroom_pickup_is_locked_and_cannot_be_overridden_by_post(flask_client):
    """Pickup mode forces showroom address on HTML, session, and return location."""
    _login_session(flask_client)
    flask_client.post("/cart/add/1", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    page = flask_client.get("/checkout")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'Nhận tại showroom (Miễn phí)' in body
    assert 'value="Group 12 Showroom - District 1"' in body
    assert 'readonly' in body
    assert 'id="co-pickup-location-help"' in body

    response = flask_client.post("/checkout", data={
        "receiving_method": "PICKUP",
        "pickup_location": "999 Fake Address, TP HCM",
        "return_location": "999 Fake Address, TP HCM",
        "return_choice": "SAME_AS_PICKUP",
        "payment_method": "CASH",
    })
    assert response.status_code == 302  # terms unchecked: address still synchronized
    with flask_client.session_transaction() as sess:
        item = sess["rental_cart"][0]
        assert item["pickup_location"] == svc.SHOWROOM_LOCATION
        assert item["return_location"] == svc.SHOWROOM_LOCATION

    # AJAX path must also ignore forged pickup addresses when mode is showroom.
    response = flask_client.post("/api/cart/dates", json={
        "apply_selected": True,
        "receiving_method": "PICKUP",
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
        "pickup_location": "Tampered address",
        "return_location": "Tampered address",
    })
    assert response.status_code == 200
    assert response.get_json()["delivery_fee"] == 0
    with flask_client.session_transaction() as sess:
        assert sess["rental_cart"][0]["pickup_location"] == svc.SHOWROOM_LOCATION
        assert sess["rental_cart"][0]["return_location"] == svc.SHOWROOM_LOCATION


def test_delivery_requires_entered_address_and_calculates_fee(flask_client):
    """Delivery needs user-entered address and charges its configured fee."""
    _login_session(flask_client)
    flask_client.post("/cart/add/1", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    blank = flask_client.post("/checkout", data={
        "receiving_method": "DELIVERY",
        "pickup_location": " ",
        "return_choice": "SAME_AS_PICKUP",
        "payment_method": "CASH", "agree_terms": "on",
    }, follow_redirects=True)
    assert "Vui lòng nhập địa chỉ giao xe tận nơi.".encode("utf-8") in blank.data

    address = "37 Hai Ba Trung, Phuong Sai Gon, TP HCM"
    response = flask_client.post("/checkout", data={
        "receiving_method": "DELIVERY",
        "pickup_location": address,
        "return_location": svc.SHOWROOM_LOCATION,  # forged client-side data ignored
        "return_choice": "SAME_AS_PICKUP",
        "payment_method": "CASH",  # no terms to avoid creating order
    })
    assert response.status_code == 302
    with flask_client.session_transaction() as sess:
        item = sess["rental_cart"][0]
        assert item["pickup_location"] == address
        assert item["return_location"] == address

    totals = flask_client.post("/api/cart/summary", json={
        "receiving_method": "DELIVERY", "selected_only": True,
    })
    assert totals.status_code == 200
    assert totals.get_json()["delivery_fee"] == 100000


def test_direct_booking_pickup_mode_forces_showroom_without_touching_cart(flask_client):
    """Book Now enforces the same showroom rule and still isolates the cart."""
    _login_session(flask_client)
    direct = flask_client.post("/book-now/1", data={
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    assert direct.status_code == 302
    page = flask_client.get("/checkout?mode=now")
    assert page.status_code == 200
    assert 'readonly' in page.get_data(as_text=True)
    result = flask_client.post("/checkout?mode=now", data={
        "receiving_method": "PICKUP",
        "pickup_location": "Client-forged address",
        "return_choice": "SAME_AS_PICKUP",
        "payment_method": "CASH",
    })
    assert result.status_code == 302
    with flask_client.session_transaction() as sess:
        assert sess["direct_booking"]["pickup_location"] == svc.SHOWROOM_LOCATION
        assert not sess.get("rental_cart")

    update = flask_client.post("/api/book-now/dates", json={
        "receiving_method": "PICKUP",
        "pickup_location": "Client-forged address",
        "return_location": "Client-forged address",
        "pickup_date": "2026-12-15", "return_date": "2026-12-17",
    })
    assert update.status_code == 200
    with flask_client.session_transaction() as sess:
        assert sess["direct_booking"]["pickup_location"] == svc.SHOWROOM_LOCATION
        assert sess["direct_booking"]["return_location"] == svc.SHOWROOM_LOCATION
        assert not sess.get("rental_cart")


# ===========================================================================
# My Account / My Rentals (Shopee-inspired customer dashboard)
# ===========================================================================
def test_account_login_required_and_shows_real_profile(flask_client):
    assert "/login" in flask_client.get("/dashboard").headers["Location"]
    assert "/login" in flask_client.post("/account/profile", data={}).headers["Location"]
    _login_session(flask_client)
    page = flask_client.get("/dashboard")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "My Account" in body
    assert "Do Thu Thao" in body
    assert "thao@group12.vn" in body
    assert "My Rental Orders" in body
    assert "All Orders" in body and "Pending" in body
    assert "Confirmed" in body and "Completed" in body
    assert "Renting" in body and "Cancelled" in body
    assert "You haven\'t rented a car yet" in body


def test_account_orders_filter_search_and_rebook_link(flask_client, booking_db):
    raw, _ = booking_db
    _login_session(flask_client)
    orders = [
        (101, 1, "2026-11-21 09:00:00", "PENDING", "PICKUP", 0, 180000, 600000, "CASH"),
        (102, 1, "2026-11-20 08:00:00", "COMPLETED", "DELIVERY", 0, 390000, 1300000, "E_WALLET"),
        (103, 2, "2026-11-19 09:00:00", "CANCELLED", "PICKUP", 0, 180000, 600000, "CASH"),
    ]
    raw.executemany(
        """INSERT INTO Orders(oderID,useID,orderTime,status,receivingMethod,
        deliveryFee,deposit,totalPrice,paymentMethod) VALUES (?,?,?,?,?,?,?,?,?)""",
        orders,
    )
    raw.executemany(
        """INSERT INTO Oderitem(OderID,CarID,unitPrice,rentalDays,pickupDate,returnDate)
           VALUES (?,?,?,?,?,?)""",
        [
            (101, 1, 600000, 1, "2026-12-15", "2026-12-16"),
            (102, 2, 650000, 2, "2026-12-17", "2026-12-19"),
            (103, 1, 600000, 1, "2026-12-15", "2026-12-16"),
        ],
    )

    all_page = flask_client.get("/dashboard").get_data(as_text=True)
    assert "RENTAL ORDER #101" in all_page
    assert "RENTAL ORDER #102" in all_page
    assert "RENTAL ORDER #103" not in all_page   # user owns only 101 and 102
    assert "/cars/1" in all_page and "/cars/2" in all_page

    pending = flask_client.get("/dashboard?status=pending").get_data(as_text=True)
    assert "RENTAL ORDER #101" in pending
    assert "RENTAL ORDER #102" not in pending
    assert "Cancel Order" in pending
    completed = flask_client.get("/dashboard?status=completed").get_data(as_text=True)
    assert "RENTAL ORDER #102" in completed
    assert "RENTAL ORDER #101" not in completed
    assert "Cancel Order" not in completed

    search = flask_client.get("/dashboard?q=Honda+City").get_data(as_text=True)
    assert "RENTAL ORDER #102" in search and "RENTAL ORDER #101" not in search
    search_number = flask_client.get("/dashboard?q=101").get_data(as_text=True)
    assert "RENTAL ORDER #101" in search_number and "RENTAL ORDER #102" not in search_number


def test_account_profile_edits_only_signed_in_user(flask_client, booking_db):
    raw, _ = booking_db
    _login_session(flask_client)
    page = flask_client.get("/dashboard?section=profile")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "My Profile" in html and "thao@group12.vn" in html
    assert 'name="csrf_token"' in html
    assert 'id="account-email"' in html
    assert 'readonly' in html
    with flask_client.session_transaction() as s:
        csrf = s["account_profile_csrf"]

    updated = flask_client.post("/account/profile", data={
        "csrf_token": csrf,
        "full_name": "Nguyen Gia Ky",
        "phone": "0976543210",
        "address": "District 1, HCMC",
        "email": "forged@example.com",
        "role": "ADMIN",
    }, follow_redirects=True)
    assert updated.status_code == 200
    assert "Nguyen Gia Ky" in updated.get_data(as_text=True)
    row = raw.execute("SELECT fullName, phone, address, email, role FROM Users WHERE UserID=1").fetchone()
    assert row["fullName"] == "Nguyen Gia Ky"
    assert row["phone"] == "0976543210"
    assert row["address"] == "District 1, HCMC"
    assert row["email"] == "thao@group12.vn"
    assert row["role"] == "CUSTOMER"
    with flask_client.session_transaction() as s:
        assert s["full_name"] == "Nguyen Gia Ky"


def test_account_profile_blocks_csrf_duplicates_and_bad_phone(flask_client, booking_db):
    raw, _ = booking_db
    _login_session(flask_client)
    assert flask_client.post("/account/profile", data={
        "full_name": "Fake Name", "phone": "0981234567",
    }).status_code == 400
    flask_client.get("/dashboard?section=profile")
    with flask_client.session_transaction() as s:
        csrf = s["account_profile_csrf"]

    bad = flask_client.post("/account/profile", data={
        "csrf_token": csrf, "full_name": "Do Thu Thao", "phone": "123",
    }, follow_redirects=True)
    assert "Please enter a valid phone number." in bad.get_data(as_text=True)

    duplicate = flask_client.post("/account/profile", data={
        "csrf_token": csrf, "full_name": "Do Thu Thao",
        "phone": "0987654321", "address": "Other",
    }, follow_redirects=True)
    assert "This phone number is already used by another account." in duplicate.get_data(as_text=True)
    row = raw.execute("SELECT phone, address FROM Users WHERE UserID=1").fetchone()
    assert row["phone"] == "0912345678"
    assert row["address"] is None


def test_account_static_copy_is_english_only():
    """Every literal display string in the My Account template uses English."""
    from pathlib import Path
    import re
    template = (Path(__file__).resolve().parents[1] /
                "presentation" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert not re.search(r"[À-ÖØ-öø-ỹ]", template)
    assert "My Rental Orders" in template
    assert "Pick up at Showroom" in template
    assert "Your profile has been updated" not in template



# ===========================================================================
# Payment integration regression tests (demo only, no real gateway)
# ===========================================================================
def test_online_deposit_payment_persists_atomically(booking_db):
    raw, tracker = booking_db
    from datetime import timedelta
    from business import payment_service
    start = date.today() + timedelta(days=15)
    end = start + timedelta(days=2)
    cart = [{"car_id": 1, "pickup_date": start.isoformat(),
             "return_date": end.isoformat(), "selected": True}]
    order_id = svc.place_order(1, cart, "PICKUP", "E_WALLET")
    row = raw.execute(
        "SELECT amount, paymentMethod, paymentStatus, transactionCode FROM Payments WHERE oderID = ?",
        (order_id,),
    ).fetchone()
    assert row["paymentStatus"] == "Paid"
    assert row["paymentMethod"] == "E_WALLET"
    assert row["amount"] == 360000
    assert row["transactionCode"].startswith("DEMO-")
    assert payment_service.balance_due(1200000, row["paymentStatus"], row["amount"]) == 840000


def test_declined_demo_payment_rolls_back_order_and_items(booking_db):
    raw, tracker = booking_db
    from datetime import timedelta
    start = date.today() + timedelta(days=25)
    end = start + timedelta(days=1)
    cart = [{"car_id": 1, "pickup_date": start.isoformat(),
             "return_date": end.isoformat(), "selected": True}]
    with pytest.raises(svc.BookingError, match="declined"):
        svc.place_order(1, cart, "PICKUP", "E_WALLET", demo_outcome="declined")
    for table in ("Orders", "Oderitem", "Payments"):
        assert raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert tracker["rollbacks"] > 0


def test_offline_payment_statuses_and_cancellation(booking_db):
    raw, tracker = booking_db
    from datetime import timedelta
    start = date.today() + timedelta(days=35)
    end = start + timedelta(days=1)
    cart = [{"car_id": 1, "pickup_date": start.isoformat(),
             "return_date": end.isoformat(), "selected": True}]
    order_id = svc.place_order(1, cart, "PICKUP", "BANK_TRANSFER")
    payment = raw.execute(
        "SELECT paymentStatus, amount FROM Payments WHERE oderID = ?", (order_id,)
    ).fetchone()
    assert payment["paymentStatus"] == "Pending"
    assert payment["amount"] == 180000
    svc.cancel_order(1, order_id)
    payment = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE oderID = ?", (order_id,)
    ).fetchone()
    assert payment["paymentStatus"] == "Cancelled"


def test_paid_demo_order_cancel_requires_real_refund(booking_db):
    raw, tracker = booking_db
    from datetime import timedelta
    start = date.today() + timedelta(days=38)
    end = start + timedelta(days=1)
    cart = [{"car_id": 1, "pickup_date": start.isoformat(),
             "return_date": end.isoformat(), "selected": True}]
    order_id = svc.place_order(1, cart, "PICKUP", "E_WALLET")
    svc.cancel_order(1, order_id)
    assert raw.execute(
        "SELECT paymentStatus FROM Payments WHERE oderID = ?", (order_id,)
    ).fetchone()[0] == "Refund Pending"


def test_payment_receipt_is_customer_scoped(flask_client, booking_db):
    raw, _ = booking_db
    from datetime import timedelta
    start = date.today() + timedelta(days=42)
    end = start + timedelta(days=1)
    cart = [{"car_id": 1, "pickup_date": start.isoformat(),
             "return_date": end.isoformat(), "selected": True}]
    order_id = svc.place_order(1, cart, "PICKUP", "E_WALLET")
    _login_session(flask_client, user_id=1)
    good = flask_client.get(f"/orders/{order_id}/payment")
    assert good.status_code == 200
    assert b"Remaining balance" in good.data
    _login_session(flask_client, user_id=2)
    denied = flask_client.get(f"/orders/{order_id}/payment")
    assert denied.status_code == 404


def test_demo_checkout_payment_decline_preserves_cart(flask_client, booking_db):
    from datetime import timedelta
    raw, _ = booking_db
    _login_session(flask_client)
    start = (date.today() + timedelta(days=43)).isoformat()
    end = (date.today() + timedelta(days=44)).isoformat()
    flask_client.post("/cart/add/1", data={"pickup_date": start, "return_date": end})
    response = flask_client.post("/checkout", data={
        "pickup_date": start, "return_date": end,
        "receiving_method": "PICKUP", "payment_method": "E_WALLET",
        "agree_terms": "on",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/payment")
    with flask_client.session_transaction() as sess:
        assert len(sess.get("rental_cart", [])) == 1
        token = sess["pending_payment"]["csrf"]
    response = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "declined",
    })
    assert response.status_code == 200
    assert b"No order was placed" in response.data
    with flask_client.session_transaction() as sess:
        assert len(sess.get("rental_cart", [])) == 1
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0



def test_payment_insert_failure_rolls_back_booking(booking_db, monkeypatch):
    raw, tracker = booking_db
    from datetime import timedelta
    from data import payment_repository
    start = date.today() + timedelta(days=46)
    end = start + timedelta(days=1)
    cart = [{"car_id": 1, "pickup_date": start.isoformat(),
             "return_date": end.isoformat(), "selected": True}]

    def fail_payment(*args, **kwargs):
        raise RuntimeError("simulated DB insert failure")

    monkeypatch.setattr(payment_repository, "insert_payment", fail_payment)
    with pytest.raises(svc.BookingError, match="ROLLBACK"):
        svc.place_order(1, cart, "PICKUP", "E_WALLET")
    for table in ("Orders", "Oderitem", "Payments"):
        assert raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert tracker["rollbacks"] > 0



def test_payment_requires_checkout_login_csrf_and_expiry(flask_client, booking_db):
    from datetime import timedelta
    import time as time_module
    raw, _ = booking_db
    assert "/login" in flask_client.get("/payment").headers["Location"]
    _login_session(flask_client)
    assert flask_client.get("/payment").status_code == 302
    pickup = (date.today() + timedelta(days=48)).isoformat()
    return_ = (date.today() + timedelta(days=49)).isoformat()
    flask_client.post("/cart/add/1", data={
        "pickup_date": pickup, "return_date": return_
    })
    begin = flask_client.post("/checkout", data={
        "pickup_date": pickup, "return_date": return_,
        "payment_method": "E_WALLET",
        "receiving_method": "PICKUP", "agree_terms": "on",
    })
    assert begin.status_code == 302
    assert begin.headers["Location"].endswith("/payment")
    assert flask_client.post("/payment", data={
        "payment_csrf": "forged", "payment_action": "confirm",
    }).status_code == 400
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0
    with flask_client.session_transaction() as sess:
        sess["pending_payment"] = {**sess["pending_payment"], "created_at": int(time_module.time()) - 3600}
    assert flask_client.get("/payment").status_code == 302
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


def test_payment_draft_separate_page_and_confirmation_recheck(flask_client, booking_db):
    from datetime import timedelta
    raw, _ = booking_db
    _login_session(flask_client)
    pickup = (date.today() + timedelta(days=50)).isoformat()
    return_ = (date.today() + timedelta(days=51)).isoformat()
    flask_client.post("/cart/add/1", data={
        "pickup_date": pickup, "return_date": return_
    })
    begin = flask_client.post("/checkout", data={
        "pickup_date": pickup, "return_date": return_,
        "payment_method": "E_WALLET",
        "receiving_method": "PICKUP", "agree_terms": "on",
    })
    assert begin.status_code == 302
    page = flask_client.get("/payment")
    assert page.status_code == 200
    assert b"E-Wallet" in page.data
    assert b"Simulate Successful Payment" in page.data
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0

    # Availability could change between Checkout and Payment.
    raw.execute("UPDATE Cars SET status = 'maintenance' WHERE carID = 1")
    with flask_client.session_transaction() as sess:
        token = sess["pending_payment"]["csrf"]
    payment = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert payment.status_code == 302
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0


def test_payment_csrf_prevents_payment_replay(flask_client, booking_db):
    from datetime import timedelta
    raw, _ = booking_db
    _login_session(flask_client)
    pickup = (date.today() + timedelta(days=52)).isoformat()
    return_ = (date.today() + timedelta(days=53)).isoformat()
    flask_client.post("/cart/add/1", data={
        "pickup_date": pickup, "return_date": return_
    })
    flask_client.post("/checkout", data={
        "pickup_date": pickup, "return_date": return_,
        "payment_method": "E_WALLET", "receiving_method": "PICKUP",
        "agree_terms": "on",
    })
    with flask_client.session_transaction() as sess:
        token = sess["pending_payment"]["csrf"]
    first = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert first.status_code == 302
    replay = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert replay.status_code == 302
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 1


def test_credit_debit_card_option_is_removed_and_rejected(flask_client, booking_db):
    """No credit/debit card option in Checkout, and forged CARD input is rejected."""
    from datetime import timedelta
    raw, _ = booking_db
    _login_session(flask_client)
    pickup = (date.today() + timedelta(days=54)).isoformat()
    return_ = (date.today() + timedelta(days=55)).isoformat()
    cart_item = {
        "car_id": 1, "pickup_date": pickup, "return_date": return_,
        "selected": True,
    }

    with pytest.raises(svc.BookingError, match="Phương thức thanh toán"):
        svc.place_order(1, [cart_item], "PICKUP", "CARD")
    flask_client.post("/cart/add/1", data={
        "pickup_date": pickup, "return_date": return_,
    })
    checkout_page = flask_client.get("/checkout")
    html = checkout_page.get_data(as_text=True)
    assert checkout_page.status_code == 200
    assert 'value="CARD"' not in html
    assert "Credit / Debit" not in html
    assert html.count('name="payment_method"') == 3
    for supported in ("E_WALLET", "BANK_TRANSFER", "CASH"):
        assert f'value="{supported}"' in html

    forged = flask_client.post("/checkout", data={
        "pickup_date": pickup, "return_date": return_,
        "receiving_method": "PICKUP",
        "payment_method": "CARD",
        "agree_terms": "on",
    })
    assert forged.status_code == 302
    assert forged.headers["Location"].startswith("/checkout")
    with flask_client.session_transaction() as sess:
        assert "pending_payment" not in sess
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0



def test_bank_vietqr_link_prefills_deposit_and_unique_reference(monkeypatch):
    from business import payment_qr
    from urllib.parse import urlparse, parse_qs

    monkeypatch.delenv("PAYMENT_BANK_BIN", raising=False)
    monkeypatch.delenv("PAYMENT_BANK_ACCOUNT", raising=False)
    assert payment_qr.bank_transfer_qr(180000, "G12TEST123") is None

    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")  # dummy test account
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "GROUP12 DEMO")
    url = payment_qr.bank_transfer_qr(180000, "G12TEST123")
    assert url.startswith("https://img.vietqr.io/image/970436-0000000000-compact2.png?")
    query = parse_qs(urlparse(url).query)
    assert query["amount"] == ["180000"]
    assert query["addInfo"] == ["G12TEST123"]
    assert query["accountName"] == ["GROUP12 DEMO"]

    # A malformed destination must never generate a QR image.
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000/attack")
    assert payment_qr.bank_transfer_qr(180000, "G12TEST123") is None


def test_momo_qr_requires_safe_filename_and_real_file(monkeypatch, flask_client, booking_db, tmp_path):
    from datetime import timedelta
    from business import payment_qr
    import run as app_module

    monkeypatch.setenv("MOMO_MERCHANT_QR_FILENAME", "../other.png")
    assert payment_qr.momo_merchant_qr_filename() is None
    monkeypatch.setenv("MOMO_MERCHANT_QR_FILENAME", "merchant.png")
    assert payment_qr.momo_merchant_qr_filename() == "merchant.png"

    _login_session(flask_client)
    pickup = (date.today() + timedelta(days=60)).isoformat()
    return_ = (date.today() + timedelta(days=61)).isoformat()
    flask_client.post("/cart/add/1", data={"pickup_date": pickup, "return_date": return_})
    flask_client.post("/checkout", data={
        "pickup_date": pickup, "return_date": return_,
        "payment_method": "E_WALLET", "receiving_method": "PICKUP",
        "agree_terms": "on",
    })
    not_configured = flask_client.get("/payment").get_data(as_text=True)
    assert "MoMo QR is not configured yet" in not_configured

    qr_dir = tmp_path / "images" / "payments"
    qr_dir.mkdir(parents=True)
    (qr_dir / "merchant.png").write_bytes(b"mock image content")
    monkeypatch.setattr(app_module.app, "static_folder", str(tmp_path))
    configured = flask_client.get("/payment").get_data(as_text=True)
    assert "/static/images/payments/merchant.png" in configured
    assert "MoMo merchant QR" in configured
    assert "Simulate Successful Payment" in configured


def test_bank_transfer_payment_page_shows_vietqr_when_configured(flask_client, booking_db, monkeypatch):
    from datetime import timedelta
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")  # dummy test account
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "GROUP12 DEMO")

    _login_session(flask_client)
    pickup = (date.today() + timedelta(days=62)).isoformat()
    return_ = (date.today() + timedelta(days=63)).isoformat()
    flask_client.post("/cart/add/1", data={"pickup_date": pickup, "return_date": return_})
    response = flask_client.post("/checkout", data={
        "pickup_date": pickup, "return_date": return_,
        "payment_method": "BANK_TRANSFER", "receiving_method": "PICKUP",
        "agree_terms": "on",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/payment")
    page = flask_client.get("/payment")
    text = page.get_data(as_text=True)
    assert "Scan VietQR to transfer the deposit" in text
    assert "img.vietqr.io/image/970436-0000000000-compact2.png" in text
    assert "amount=180000" in text
    assert "G12" in text
    with flask_client.session_transaction() as sess:
        reference = sess["pending_payment"]["transfer_reference"]
        token = sess["pending_payment"]["csrf"]
        assert reference.startswith("G12")
        assert reference in text
    raw, _ = booking_db
    assert raw.execute("SELECT COUNT(*) FROM Orders").fetchone()[0] == 0

    confirmed = flask_client.post("/payment", data={
        "payment_csrf": token, "payment_action": "confirm",
    })
    assert confirmed.status_code == 302
    saved = raw.execute(
        "SELECT transactionCode, paymentStatus FROM Payments LIMIT 1"
    ).fetchone()
    assert saved["transactionCode"] == reference
    assert saved["paymentStatus"] == "Pending"



# ===========================================================================
# Two-stage payments: 30% verified deposit + 70% remaining amount.
# ===========================================================================
def _customer_order_for_balance():
    from datetime import timedelta
    start = date.today() + timedelta(days=23)
    end = start + timedelta(days=1)
    return [{
        "car_id": 1, "pickup_date": start.isoformat(),
        "return_date": end.isoformat(), "selected": True,
    }]


def _seed_admin(raw):
    raw.execute(
        """INSERT INTO Users
           (UserID, fullName, phone, email, passwordHash, role, isLocked)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (3, "Payment Admin", "0900000000", "admin@group12.vn", "hash", "ADMIN", 0),
    )


def test_remaining_requires_verified_deposit_and_does_not_double_count(booking_db):
    from business import payment_collection_service as col
    raw, tracker = booking_db
    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "BANK_TRANSFER")
    # Original bank deposit exists as Pending, so the customer cannot collect 70% yet.
    with pytest.raises(col.CollectionError, match="deposit must be verified"):
        col.request_remaining_payment(1, order_id, "CASH")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1

    deposit_id = raw.execute(
        "SELECT paymentID FROM Payments WHERE oderID = ?", (order_id,)
    ).fetchone()[0]
    col.confirm_collection(deposit_id)
    overview = svc.get_order_payment_details(1, order_id)
    assert overview["paid_amount"] == Decimal("180000")
    assert overview["pending_amount"] == Decimal("0")
    assert overview["balance_due"] == Decimal("420000")
    assert overview["can_pay_remaining"]
    assert overview["payment_status"] == "Partially Paid"

    payment_id = col.request_remaining_payment(1, order_id, "CASH")
    with pytest.raises(col.CollectionError, match="awaiting verification"):
        col.request_remaining_payment(1, order_id, "BANK_TRANSFER")
    row = raw.execute(
        "SELECT amount, paymentMethod, paymentStatus FROM Payments WHERE paymentID = ?",
        (payment_id,),
    ).fetchone()
    assert row["amount"] == 420000
    assert row["paymentMethod"] == "CASH"
    assert row["paymentStatus"] == "Pending"
    view = svc.get_order_payment_details(1, order_id)
    assert view["paid_amount"] == Decimal("180000")
    assert view["pending_amount"] == Decimal("420000")
    assert view["balance_due"] == Decimal("420000")
    assert view["pending_balance_request"]


def test_staff_confirmation_pays_full_balance_only_once(booking_db):
    from business import payment_collection_service as col
    raw, _ = booking_db
    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "E_WALLET")
    payment_id = col.request_remaining_payment(1, order_id, "BANK_TRANSFER")

    queue = col.list_pending_collections()
    assert len(queue) == 1
    assert queue[0]["paymentID"] == payment_id
    assert queue[0]["customerName"] == "Do Thu Thao"
    assert queue[0]["amount"] == 420000

    assert col.confirm_collection(payment_id) == order_id
    with pytest.raises(col.CollectionError, match="not Pending"):
        col.confirm_collection(payment_id)
    view = svc.get_order_payment_details(1, order_id)
    assert view["paid_amount"] == Decimal("600000")
    assert view["balance_due"] == Decimal("0")
    assert view["payment_status"] == "Paid in Full"
    assert not view["can_pay_remaining"]
    assert len(view["payments"]) == 2
    with pytest.raises(col.CollectionError, match="deposit must be verified"):
        col.request_remaining_payment(1, order_id, "E_WALLET")


def test_balance_change_method_cancels_only_pending_balance_request(booking_db):
    from business import payment_collection_service as col
    raw, _ = booking_db
    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "E_WALLET")
    pending_id = col.request_remaining_payment(1, order_id, "E_WALLET")
    assert col.cancel_remaining_request(1, order_id)
    assert raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID = ?", (pending_id,)
    ).fetchone()[0] == "Cancelled"
    assert raw.execute(
        "SELECT paymentStatus FROM Payments WHERE oderID = ? ORDER BY paymentID ASC",
        (order_id,),
    ).fetchone()[0] == "Paid"
    new_id = col.request_remaining_payment(1, order_id, "CASH")
    assert new_id != pending_id
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 3
    with pytest.raises(col.CollectionError, match="not found"):
        col.cancel_remaining_request(2, order_id)


def test_pay_remaining_ui_qr_and_access_control(flask_client, booking_db, monkeypatch):
    from business import payment_collection_service as col
    raw, _ = booking_db
    monkeypatch.setenv("PAYMENT_BANK_BIN", "970436")
    monkeypatch.setenv("PAYMENT_BANK_ACCOUNT", "0000000000")  # test-only account
    monkeypatch.setenv("PAYMENT_BANK_HOLDER", "GROUP 12 TEST")

    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "E_WALLET")
    assert "/login" in flask_client.get(
        f"/orders/{order_id}/pay-remaining"
    ).headers["Location"]
    _login_session(flask_client, user_id=2)
    assert flask_client.get(f"/orders/{order_id}/pay-remaining").status_code == 404

    _login_session(flask_client, user_id=1)
    view = flask_client.get(f"/orders/{order_id}/pay-remaining")
    assert view.status_code == 200
    assert b"Pay Remaining Balance" in view.data
    with flask_client.session_transaction() as sess:
        csrf = sess["collection_csrf"]
    invalid = flask_client.post(f"/orders/{order_id}/pay-remaining", data={
        "csrf_token": "invalid", "action": "request", "payment_method": "BANK_TRANSFER",
    })
    assert invalid.status_code == 400
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == 1

    submit = flask_client.post(f"/orders/{order_id}/pay-remaining", data={
        "csrf_token": csrf, "action": "request", "payment_method": "BANK_TRANSFER",
    })
    assert submit.status_code == 302
    page = flask_client.get(f"/orders/{order_id}/pay-remaining")
    body = page.get_data(as_text=True)
    assert "img.vietqr.io/image/970436-0000000000-compact2.png" in body
    assert "amount=420000" in body
    assert "Awaiting Verification" in body
    assert "BAL-" in body
    assert "Review Payment" in flask_client.get("/dashboard").get_data(as_text=True)
    assert raw.execute(
        "SELECT COUNT(*) FROM Payments WHERE paymentStatus = 'Paid'"
    ).fetchone()[0] == 1

    cancel = flask_client.post(f"/orders/{order_id}/pay-remaining", data={
        "csrf_token": csrf, "action": "cancel_pending",
    })
    assert cancel.status_code == 302
    assert svc.get_order_payment_details(1, order_id)["can_pay_remaining"]


def test_admin_payment_verification_rejects_customers_and_csrf(flask_client, booking_db):
    from business import payment_collection_service as col
    raw, _ = booking_db
    _seed_admin(raw)
    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "BANK_TRANSFER")
    payment_id = raw.execute("SELECT paymentID FROM Payments LIMIT 1").fetchone()[0]
    assert "/login" in flask_client.get("/admin/payments").headers["Location"]
    _login_session(flask_client, user_id=1)
    assert flask_client.get("/admin/payments").status_code == 403

    _login_session(flask_client, user_id=3)
    with flask_client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    admin_page = flask_client.get("/admin/payments")
    assert admin_page.status_code == 200
    assert b"Payment Verification" in admin_page.data
    with flask_client.session_transaction() as sess:
        token = sess["admin_payment_csrf"]
    route = f"/admin/payments/{payment_id}/confirm"
    assert flask_client.post(route, data={"csrf_token": "wrong", "verified": "yes"}).status_code == 400
    skip = flask_client.post(route, data={"csrf_token": token})
    assert skip.status_code == 302
    assert raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID = ?", (payment_id,)
    ).fetchone()[0] == "Pending"

    confirm = flask_client.post(route, data={
        "csrf_token": token, "verified": "yes",
    })
    assert confirm.status_code == 302
    assert raw.execute(
        "SELECT paymentStatus FROM Payments WHERE paymentID = ?", (payment_id,)
    ).fetchone()[0] == "Paid"
    assert svc.get_order_payment_details(1, order_id)["can_pay_remaining"]
    # Repeated verification must never credit the same transaction twice.
    flask_client.post(route, data={"csrf_token": token, "verified": "yes"})
    assert raw.execute(
        "SELECT COUNT(*) FROM Payments WHERE paymentStatus = 'Paid'"
    ).fetchone()[0] == 1


def test_admin_db_role_is_rechecked_even_if_session_claims_admin(flask_client, booking_db):
    raw, _ = booking_db
    _login_session(flask_client, user_id=1)
    with flask_client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    assert flask_client.get("/admin/payments").status_code == 403

    _seed_admin(raw)
    _login_session(flask_client, user_id=3)
    with flask_client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    assert flask_client.get("/admin/payments").status_code == 200
    raw.execute("UPDATE Users SET isLocked = 1 WHERE UserID = 3")
    assert flask_client.get("/admin/payments").status_code == 403


def test_cancel_order_marks_all_pending_and_manual_refund_required(booking_db):
    from business import payment_collection_service as col
    raw, _ = booking_db
    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "E_WALLET")
    pending_id = col.request_remaining_payment(1, order_id, "CASH")
    svc.cancel_order(1, order_id)
    rows = raw.execute(
        "SELECT paymentStatus FROM Payments WHERE oderID = ? ORDER BY paymentID ASC",
        (order_id,),
    ).fetchall()
    assert [r[0] for r in rows] == ["Refund Pending", "Cancelled"]
    with pytest.raises(col.CollectionError, match="cancelled order"):
        col.confirm_collection(pending_id)
    assert not svc.get_order_payment_details(1, order_id)["can_pay_remaining"]


def test_remainder_request_db_failure_rolls_back(booking_db, monkeypatch):
    from business import payment_collection_service as col
    from data import payment_repository
    raw, tracker = booking_db
    order_id = svc.place_order(1, _customer_order_for_balance(), "PICKUP", "E_WALLET")
    initial = raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0]

    def crash(*args, **kwargs):
        raise RuntimeError("simulated SQL error")

    monkeypatch.setattr(payment_repository, "insert_payment", crash)
    with pytest.raises(col.CollectionError, match="Unable to create payment"):
        col.request_remaining_payment(1, order_id, "CASH")
    assert raw.execute("SELECT COUNT(*) FROM Payments").fetchone()[0] == initial
    assert tracker["rollbacks"] > 0
