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
    order_id = svc.place_order(1, cart1, "PICKUP", "CARD", today=today)
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
        svc.place_order(1, cart, receiving_method="PICKUP", payment_method="CARD", today=today)

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


def test_full_web_booking_flow_cart_to_checkout_to_cancel(flask_client):
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
            "payment_method": "CARD",
        },
        follow_redirects=True,
    )
    assert "Điều khoản".encode("utf-8") in co_no_terms.data

    # 7. Submit Checkout with terms agreed -> creates order #1, redirects to /orders
    co_ok = flask_client.post(
        "/checkout",
        data={
            "pickup_date": "2026-12-10",
            "return_date": "2026-12-13",
            "pickup_location": "Tan Son Nhat Airport",
            "return_location": "Tan Son Nhat Airport",
            "receiving_method": "PICKUP",
            "payment_method": "CARD",
            "agree_terms": "on",
        },
        follow_redirects=True,
    )
    assert co_ok.status_code == 200
    assert b"#1" in co_ok.data
    assert b"Toyota Vios" in co_ok.data

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
        assert car_img_url("/static/images/booking/car_vios.svg") == "/static/images/booking/car_vios.svg"
        assert car_img_url("https://example.com/car.jpg") == "https://example.com/car.jpg"
        assert car_img_url("") == "/static/images/booking/car_vios.svg"

    _login_session(flask_client, user_id=1, full_name="Do Thu Thao")
    res = flask_client.get("/cart")
    assert res.status_code == 200
    assert b"/static/images/cars/toyotavios2023.webp" in res.data
    assert b"/static/images/cars/hondacity2022.webp" in res.data
