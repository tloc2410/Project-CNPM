"""Standalone SQLite preview for booking UI; production uses run.py and MySQL."""

import os
import re
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal

os.environ.setdefault("SECRET_KEY", "group12-local-preview-secret")

from flask import redirect, session, url_for

from data import database
import run as app_module

DB_FILE = os.path.join(tempfile.gettempdir(), "group12_booking_preview.sqlite3")


class _PreviewCursor:
    def __init__(self, conn, dictionary=False):
        self._cur = conn.cursor()
        self._dictionary = dictionary
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        adapted = sql.replace("%s", "?")
        adapted = re.sub(r"\bFOR\s+UPDATE\b", "", adapted, flags=re.IGNORECASE)
        vals = []
        for p in (params or ()):
            if isinstance(p, Decimal):
                vals.append(float(p))
            elif isinstance(p, datetime):
                vals.append(p.strftime("%Y-%m-%d %H:%M:%S"))
            elif isinstance(p, date):
                vals.append(p.isoformat())
            else:
                vals.append(p)
        self._cur.execute(adapted, tuple(vals))
        self.lastrowid = self._cur.lastrowid
        self.rowcount = self._cur.rowcount

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row) if self._dictionary else tuple(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows] if self._dictionary else [tuple(r) for r in rows]

    def close(self):
        self._cur.close()


class _PreviewConnection:
    def __init__(self, db_path):
        self._raw = sqlite3.connect(db_path, isolation_level=None)
        self._raw.row_factory = sqlite3.Row
        self._raw.execute("PRAGMA foreign_keys = ON")

    def cursor(self, dictionary=False):
        return _PreviewCursor(self._raw, dictionary=dictionary)

    def start_transaction(self):
        if not self._raw.in_transaction:
            self._raw.execute("BEGIN")

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _init_preview_db():
    conn = sqlite3.connect(DB_FILE)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS Users (
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
        CREATE TABLE IF NOT EXISTS CarTypes (
            typeId INTEGER PRIMARY KEY AUTOINCREMENT,
            typeName TEXT NOT NULL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS Cars (
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
        CREATE TABLE IF NOT EXISTS Orders (
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
        CREATE TABLE IF NOT EXISTS Oderitem (
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
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO Users (UserID, fullName, phone, email, passwordHash, role)
        VALUES (1, 'Đỗ Thu Thảo', '0912345678', 'thao@group12.vn', 'preview-only', 'CUSTOMER')
        """
    )
    conn.executemany(
        "INSERT OR IGNORE INTO CarTypes (typeId, typeName, description) VALUES (?, ?, ?)",
        [
            (1, "Sedan 4 chỗ", "Sedan"),
            (2, "Xe điện SUV", "Electric"),
            (3, "MPV 7 chỗ", "Family MPV"),
        ],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO Cars
            (carID, TypeID, code, name, pictures, description, numberOfSeats, pricePerDay, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 1, "SEDAN-01", "Toyota Vios 2023", "toyotavios2023.webp", "Automatic · Petrol", 5, 850000.0, "available"),
            (2, 1, "SEDAN-02", "Honda City 2022", "hondacity2022.webp", "Automatic · Petrol", 5, 900000.0, "available"),
            (3, 2, "SUV-01", "Toyota Corolla Cross", "toyotacorollacross.webp", "Automatic · SUV", 5, 1250000.0, "available"),
            (4, 2, "SUV-02", "Mazda CX-5 2023", "mazdacx-52023.webp", "Automatic · SUV", 5, 1400000.0, "available"),
            (5, 3, "ELEC-01", "VinFast VF e34", "vinfastVFe34.webp", "Automatic · Electric", 5, 1100000.0, "available"),
        ],
    )
    conn.commit()
    conn.close()


_init_preview_db()
database.get_db_connection = lambda: _PreviewConnection(DB_FILE)

app = app_module.app


@app.route("/preview-start")
def preview_start():
    """Auto-sign-in demo customer and pre-fill 2 Figma cars in cart for quick review."""
    session["user_id"] = 1
    session["full_name"] = "Đỗ Thu Thảo"
    session["role"] = "CUSTOMER"
    p = (date.today() + timedelta(days=1)).isoformat()
    r = (date.today() + timedelta(days=2)).isoformat()
    session["rental_cart"] = [
        {
            "car_id": 1,
            "pickup_date": p,
            "return_date": r,
            "selected": True,
            "pickup_location": "Tan Son Nhat Airport",
            "return_location": "Tan Son Nhat Airport",
        },
        {
            "car_id": 2,
            "pickup_date": p,
            "return_date": r,
            "selected": False,
            "pickup_location": "Tan Son Nhat Airport",
            "return_location": "Tan Son Nhat Airport",
        },
    ]
    session.modified = True
    return redirect(url_for("booking.cart"))


if __name__ == "__main__":
    print("Group 12 Booking Preview running at:")
    print("  -> http://127.0.0.1:5000/preview-start (Auto-login + 2 sample cars)")
    print("  -> http://127.0.0.1:5000/cart")
    print("  -> http://127.0.0.1:5000/checkout")
    print("  -> http://127.0.0.1:5000/orders")
    app.run(host="127.0.0.1", port=5000, debug=False)
