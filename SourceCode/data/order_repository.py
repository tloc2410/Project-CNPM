from data.database import get_db_connection


def get_order_by_id(order_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT oderID,
                   useID,
                   orderTime,
                   status,
                   receivingMethod,
                   deliveryFee,
                   deposit,
                   totalPrice,
                   paymentMethod
            FROM orders
            WHERE oderID = %s
            """,
            (order_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_all_orders_with_customer():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT o.oderID,
                   MAX(o.useID) AS useID,
                   MAX(o.orderTime) AS orderTime,
                   MAX(o.status) AS status,
                   MAX(o.receivingMethod) AS receivingMethod,
                   MAX(o.deliveryFee) AS deliveryFee,
                   MAX(o.deposit) AS deposit,
                   MAX(o.totalPrice) AS totalPrice,
                   COALESCE(MAX(p.paymentMethod), MAX(o.paymentMethod)) AS paymentMethod,
                   NULL AS paymentStatus,
                   MAX(u.fullName) AS fullName,
                   MAX(u.email) AS email
            FROM orders o
            LEFT JOIN users u ON o.useID = u.UserID
            LEFT JOIN payments p ON p.oderID = o.oderID
            GROUP BY o.oderID
            ORDER BY o.oderID DESC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def update_order_status(order_id, new_status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = %s WHERE oderID = %s",
            (new_status, order_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()