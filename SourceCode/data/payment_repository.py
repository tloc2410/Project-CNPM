try:
    from data.database import get_db_connection
except ImportError:
    from SourceCode.data.database import get_db_connection


def create_payment(order_id, amount, payment_method, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            INSERT INTO Payments (oderID, amount, paymentMethod, paymentStatus, paidAt)
            VALUES (%s, %s, %s, %s, NOW())
        """
        cursor.execute(sql, (order_id, amount, payment_method, status))
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_payments_by_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM Payments WHERE oderID = %s ORDER BY paymentID DESC",
            (order_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()