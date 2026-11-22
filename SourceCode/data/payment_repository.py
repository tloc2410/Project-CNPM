"""Payment persistence; uses the caller's transaction and cursor (no commit)."""


def insert_payment(cursor, order_id, amount, method, status, transaction_code, paid_at=None):
    cursor.execute(
        """
        INSERT INTO Payments
            (oderID, amount, paymentMethod, paymentStatus, transactionCode, paidAt)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (order_id, amount, method, status, transaction_code, paid_at),
    )
    return cursor.lastrowid


def list_payments_for_orders(cursor, order_ids):
    if not order_ids:
        return []
    params = ", ".join(["%s"] * len(order_ids))
    cursor.execute(
        f"""SELECT paymentID, oderID, amount, paymentMethod, paymentStatus,
                   transactionCode, paidAt
            FROM Payments WHERE oderID IN ({params})
            ORDER BY paymentID DESC""",
        tuple(order_ids),
    )
    return cursor.fetchall()


def latest_payment_for_update(cursor, order_id):
    cursor.execute(
        """SELECT paymentID, oderID, amount, paymentMethod, paymentStatus,
                  transactionCode, paidAt
           FROM Payments
           WHERE oderID = %s ORDER BY paymentID DESC LIMIT 1 FOR UPDATE""",
        (order_id,),
    )
    return cursor.fetchone()


def update_payment_status(cursor, payment_id, status):
    cursor.execute(
        "UPDATE Payments SET paymentStatus = %s WHERE paymentID = %s",
        (status, payment_id),
    )
    return cursor.rowcount > 0



def list_pending_collections(cursor):
    """List Pending collections for staff review."""
    cursor.execute(
        """
        SELECT p.paymentID, p.oderID, p.amount, p.paymentMethod, p.paymentStatus,
               p.transactionCode, p.paidAt, o.status AS orderStatus,
               o.totalPrice, o.deposit, u.fullName AS customerName,
               u.email AS customerEmail
        FROM Payments p
        JOIN Orders o ON o.oderID = p.oderID
        JOIN Users u ON u.UserID = o.useID
        WHERE p.paymentStatus = 'Pending'
          AND UPPER(o.status) NOT IN ('CANCELLED', 'CANCELED')
        ORDER BY p.paymentID ASC
        """
    )
    return cursor.fetchall()


def mark_payment_paid(cursor, payment_id, paid_at):
    cursor.execute(
        """UPDATE Payments SET paymentStatus = 'Paid', paidAt = %s
           WHERE paymentID = %s AND paymentStatus = 'Pending'""",
        (paid_at, payment_id),
    )
    return cursor.rowcount == 1
