"""MySQL access for the Admin screens; uses the shared Group12 schema."""
# UML [Admin, CarType, Car, User, Order]: MySQL queries for Admin screens.


from data import database


def _fetch_all(sql, params=()):
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _execute(sql, params):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        count = cursor.rowcount
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def list_vehicle_types():
    return _fetch_all(
        "SELECT typeId AS id, typeName AS name, description FROM CarTypes ORDER BY typeId"
    )


def list_vehicles():
    return _fetch_all(
        """SELECT c.carID AS id, c.code AS license_plate, c.name,
                  c.TypeID AS type_id, t.typeName AS type_name,
                  c.numberOfSeats AS seats, c.pricePerDay AS daily_price,
                  c.status, c.description, c.pictures, c.numberOfViews
           FROM Cars c LEFT JOIN CarTypes t ON t.typeId = c.TypeID
           ORDER BY c.carID DESC"""
    )


def insert_vehicle(data):
    return _execute(
        """INSERT INTO Cars (TypeID, code, name, pictures, description,
                             numberOfSeats, pricePerDay, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (data["type_id"], data["license_plate"], data["name"],
         data.get("pictures", ""), data.get("description", ""),
         data["seats"], data["daily_price"], data["status"]),
    )


def edit_vehicle(vehicle_id, data):
    return _execute(
        """UPDATE Cars SET TypeID=%s, code=%s, name=%s,
                 description=COALESCE(%s, description), numberOfSeats=%s, pricePerDay=%s, status=%s
           WHERE carID=%s""",
        (data["type_id"], data["license_plate"], data["name"],
         data.get("description", ""), data["seats"],
         data["daily_price"], data["status"], vehicle_id),
    )


def change_vehicle_status(vehicle_id, status):
    return _execute("UPDATE Cars SET status=%s WHERE carID=%s",
                    (status, vehicle_id))


def remove_vehicle(vehicle_id):
    return _execute("DELETE FROM Cars WHERE carID=%s", (vehicle_id,))


def insert_vehicle_type(name, description):
    return _execute("INSERT INTO CarTypes (typeName, description) VALUES (%s, %s)",
                    (name, description))


def remove_vehicle_type(type_id):
    return _execute("DELETE FROM CarTypes WHERE typeId=%s", (type_id,))


def list_users():
    return _fetch_all(
        """SELECT UserID AS id, fullName AS full_name, email, phone, address,
                  role, isLocked AS is_locked
           FROM Users ORDER BY UserID"""
    )


def set_user_lock(user_id, locked):
    return _execute("UPDATE Users SET isLocked=%s WHERE UserID=%s",
                    (1 if locked else 0, user_id))


def list_orders():
    return _fetch_all(
        """SELECT o.oderID AS id, o.oderID AS order_code,
                  MAX(u.fullName) AS customer,
                  COALESCE(GROUP_CONCAT(c.name), '-') AS vehicle,
                  MIN(oi.pickupDate) AS pickup_date,
                  MAX(oi.returnDate) AS return_date,
                  MAX(o.totalPrice) AS total, MAX(o.deposit) AS deposit,
                  MAX(o.paymentMethod) AS payment_method,
                  MAX(o.status) AS status, MAX(o.orderTime) AS order_time
           FROM Orders o
           LEFT JOIN Users u ON u.UserID = o.useID
           LEFT JOIN Oderitem oi ON oi.OderID = o.oderID
           LEFT JOIN Cars c ON c.carID = oi.CarID
           GROUP BY o.oderID ORDER BY o.oderID DESC"""
    )


def list_payments_for_reports():
    return _fetch_all(
        """SELECT p.amount, p.paidAt, p.transactionCode, p.paymentMethod,
                  o.status AS order_status
           FROM Payments p JOIN Orders o ON o.oderID=p.oderID
           WHERE p.paymentStatus='Paid' ORDER BY p.paidAt DESC"""
    )


def update_order_status(order_id, new_status, allowed_transitions):
    """Lock order and update its payment records atomically when cancelled."""
    from data import booking_repository, payment_repository

    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        order = booking_repository.get_order_for_update(cursor, order_id)
        if not order:
            raise ValueError("Rental order not found.")
        current = str(order.get("status") or "PENDING").upper()
        if new_status not in allowed_transitions.get(current, set()):
            raise ValueError(f"Cannot change order from {current} to {new_status}.")
        if new_status == "CANCELLED":
            for p in payment_repository.list_payments_for_orders(cursor, [order_id]):
                status = str(p.get("paymentStatus") or "")
                if status == "Paid":
                    payment_repository.update_payment_status(
                        cursor, p["paymentID"], "Refund Pending"
                    )
                elif status == "Pending":
                    payment_repository.update_payment_status(
                        cursor, p["paymentID"], "Cancelled"
                    )
        booking_repository.update_order_status(cursor, order_id, new_status)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
