"""Data access layer for module Rental Cart & Booking (Do Thu Thao).

Strictly adheres to the team's shared MySQL schema in
Database/group12_car_rental.sql:
  - Users(UserID, fullName, phone, email, address, ...)
  - CarTypes(typeId, typeName, description)
  - Cars(carID, TypeID, code, name, pictures, description,
         numberOfSeats, pricePerDay, status, numberOfViews)
  - Orders(oderID, useID, orderTime, status, receivingMethod,
           deliveryFee, deposit, totalPrice, paymentMethod)
  - Oderitem(OderitemID, OderID, CarID, unitPrice, rentalDays,
             pickupDate, returnDate)

All transactional functions receive an open ``cursor`` so the business layer
exclusively controls ``start_transaction()``, ``commit()``, and ``rollback()``.
"""

# Orders in these statuses do NOT block a car's booking calendar.
INACTIVE_STATUSES = ("CANCELLED", "COMPLETED", "RETURNED")


def get_user_by_id(cursor, user_id):
    """Fetch basic renter profile info for checkout display."""
    cursor.execute(
        """
        SELECT UserID, fullName, phone, email, address
        FROM Users
        WHERE UserID = %s
        """,
        (user_id,),
    )
    return cursor.fetchone()


def get_cars_by_ids(cursor, car_ids, lock=False):
    """Return {carID: car_dict}. ``lock=True`` adds FOR UPDATE inside a transaction."""
    unique_ids = sorted({int(cid) for cid in (car_ids or [])})
    if not unique_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(unique_ids))
    if lock:
        # Lock rows in deterministic primary-key order to avoid deadlocks.
        sql = (
            "SELECT carID, TypeID, code, name, pictures, description, "
            "numberOfSeats, pricePerDay, status "
            f"FROM Cars WHERE carID IN ({placeholders}) "
            "ORDER BY carID FOR UPDATE"
        )
    else:
        sql = (
            "SELECT c.carID, c.TypeID, c.code, c.name, c.pictures, "
            "c.description, c.numberOfSeats, c.pricePerDay, c.status, "
            "ct.typeName "
            "FROM Cars c "
            "LEFT JOIN CarTypes ct ON ct.typeId = c.TypeID "
            f"WHERE c.carID IN ({placeholders}) "
            "ORDER BY c.carID"
        )
    cursor.execute(sql, tuple(unique_ids))
    return {row["carID"]: row for row in cursor.fetchall()}


def list_available_cars(cursor, keyword=""):
    """List available cars, optionally filtered by keyword on car name."""
    keyword = (keyword or "").strip()
    if keyword:
        cursor.execute(
            """
            SELECT c.carID, c.TypeID, c.code, c.name, c.pictures,
                   c.description, c.numberOfSeats, c.pricePerDay, c.status,
                   ct.typeName
            FROM Cars c
            LEFT JOIN CarTypes ct ON ct.typeId = c.TypeID
            WHERE LOWER(c.status) = 'available'
              AND LOWER(c.name) LIKE %s
            ORDER BY c.carID
            """,
            (f"%{keyword.lower()}%",),
        )
    else:
        cursor.execute(
            """
            SELECT c.carID, c.TypeID, c.code, c.name, c.pictures,
                   c.description, c.numberOfSeats, c.pricePerDay, c.status,
                   ct.typeName
            FROM Cars c
            LEFT JOIN CarTypes ct ON ct.typeId = c.TypeID
            WHERE LOWER(c.status) = 'available'
            ORDER BY c.carID
            """
        )
    return cursor.fetchall()


def find_overlapping_bookings(cursor, car_id, pickup_date, return_date):
    """Find active order items of ``car_id`` overlapping [pickup_date, return_date].

    Two inclusive date ranges [p1, r1] and [p2, r2] overlap iff:
        p1 <= r2 AND r1 >= p2.
    """
    placeholders = ", ".join(["%s"] * len(INACTIVE_STATUSES))
    sql = f"""
        SELECT oi.OderitemID, oi.OderID, oi.pickupDate, oi.returnDate, o.status
        FROM Oderitem oi
        JOIN Orders o ON o.oderID = oi.OderID
        WHERE oi.CarID = %s
          AND (o.status IS NULL OR UPPER(o.status) NOT IN ({placeholders}))
          AND oi.pickupDate <= %s
          AND oi.returnDate >= %s
        ORDER BY oi.pickupDate
    """
    cursor.execute(
        sql, (int(car_id), *INACTIVE_STATUSES, return_date, pickup_date)
    )
    return cursor.fetchall()


def insert_order(
    cursor,
    user_id,
    order_time,
    status,
    receiving_method,
    delivery_fee,
    deposit,
    total_price,
    payment_method,
):
    """Insert a new record into Orders and return its generated oderID."""
    cursor.execute(
        """
        INSERT INTO Orders (
            useID, orderTime, status, receivingMethod,
            deliveryFee, deposit, totalPrice, paymentMethod
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            order_time,
            status,
            receiving_method,
            delivery_fee,
            deposit,
            total_price,
            payment_method,
        ),
    )
    return cursor.lastrowid


def insert_order_item(
    cursor,
    order_id,
    car_id,
    unit_price,
    rental_days,
    pickup_date,
    return_date,
):
    """Insert a new record into Oderitem and return its generated OderitemID."""
    cursor.execute(
        """
        INSERT INTO Oderitem (
            OderID, CarID, unitPrice, rentalDays, pickupDate, returnDate
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (order_id, car_id, unit_price, rental_days, pickup_date, return_date),
    )
    return cursor.lastrowid


def get_order_for_update(cursor, order_id):
    """Lock and return an order row by oderID inside a transaction."""
    cursor.execute(
        """
        SELECT oderID, useID, status, totalPrice, deposit, paymentMethod
        FROM Orders
        WHERE oderID = %s
        FOR UPDATE
        """,
        (order_id,),
    )
    return cursor.fetchone()


def update_order_status(cursor, order_id, status):
    """Update status of an existing order."""
    cursor.execute(
        "UPDATE Orders SET status = %s WHERE oderID = %s",
        (status, order_id),
    )
    return cursor.rowcount


def list_orders_by_user(cursor, user_id):
    """List all orders belonging to a specific user, newest first."""
    cursor.execute(
        """
        SELECT oderID, useID, orderTime, status, receivingMethod,
               deliveryFee, deposit, totalPrice, paymentMethod
        FROM Orders
        WHERE useID = %s
        ORDER BY orderTime DESC, oderID DESC
        """,
        (user_id,),
    )
    return cursor.fetchall()


def list_items_by_order_ids(cursor, order_ids):
    """Fetch all Oderitem rows (with car metadata) for a list of order IDs."""
    if not order_ids:
        return []
    placeholders = ", ".join(["%s"] * len(order_ids))
    cursor.execute(
        f"""
        SELECT oi.OderitemID, oi.OderID, oi.CarID, oi.unitPrice, oi.rentalDays,
               oi.pickupDate, oi.returnDate,
               c.name AS carName, c.pictures, c.numberOfSeats, c.description
        FROM Oderitem oi
        JOIN Cars c ON c.carID = oi.CarID
        WHERE oi.OderID IN ({placeholders})
        ORDER BY oi.OderitemID
        """,
        tuple(order_ids),
    )
    return cursor.fetchall()
