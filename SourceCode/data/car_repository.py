"""MySQL access for the vehicle module (tables ``Cars`` and ``CarTypes``).

This module is the only place allowed to build SQL for vehicles. Business
rules and validation live in ``business.vehicle_service``.
"""
from data.database import get_db_connection

_CAR_SELECT = """
    c.carID, c.TypeID, c.code, c.name, c.pictures, c.description,
    c.numberOfSeats, c.pricePerDay, c.status, c.numberOfViews,
    t.typeName
"""

# The team schema currently spells the order-item table ``Oderitem``. Support
# the corrected spelling too, without breaking when that module is not ready.
_RENTAL_TABLE = None
_RENTAL_TABLE_RESOLVED = False


def _rental_table():
    global _RENTAL_TABLE, _RENTAL_TABLE_RESOLVED
    if _RENTAL_TABLE_RESOLVED:
        return _RENTAL_TABLE

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema = DATABASE()
                 AND table_name IN ('Oderitem', 'OrderItem')
               ORDER BY table_name
               LIMIT 1"""
        )
        row = cursor.fetchone()
        _RENTAL_TABLE = row[0] if row else None
        _RENTAL_TABLE_RESOLVED = True
        return _RENTAL_TABLE
    finally:
        cursor.close()
        connection.close()


def _rental_count_expression():
    """Return a scalar subquery for rental count, or 0 when not available."""
    table = _rental_table()
    if not table:
        return "0"
    # Table name comes from the fixed whitelist above, never from user input.
    return f"(SELECT COUNT(*) FROM `{table}` oi WHERE oi.CarID = c.carID)"


def _close(cursor, connection):
    cursor.close()
    connection.close()


def _build_filters(keyword="", type_id=None, seats_min=None, seats_max=None,
                   status=None):
    where = []
    params = []

    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        where.append(
            """(c.name LIKE %s OR c.code LIKE %s OR c.description LIKE %s
                OR t.typeName LIKE %s)"""
        )
        params.extend([like, like, like, like])

    if type_id is not None:
        where.append("c.TypeID = %s")
        params.append(type_id)

    if seats_min is not None:
        where.append("c.numberOfSeats >= %s")
        params.append(seats_min)

    if seats_max is not None:
        where.append("c.numberOfSeats <= %s")
        params.append(seats_max)

    if status:
        where.append("c.status = %s")
        params.append(status)

    clause = " WHERE " + " AND ".join(where) if where else ""
    return clause, params


_SORT_SQL = {
    "newest": "c.carID DESC",
    "oldest": "c.carID ASC",
    "name_asc": "c.name ASC",
    "price_asc": "c.pricePerDay ASC, c.carID ASC",
    "price_desc": "c.pricePerDay DESC, c.carID ASC",
    "popular": "c.numberOfViews DESC, c.carID ASC",
    "rentals_desc": "rentalCount DESC, c.carID ASC",
}


def search_cars(keyword="", type_id=None, seats_min=None, seats_max=None,
                status=None, sort="newest", limit=12, offset=0):
    """Return a page of cars joined with their type and rental count."""
    where, params = _build_filters(keyword, type_id, seats_min, seats_max,
                                  status)
    order = _SORT_SQL.get(sort, _SORT_SQL["newest"])

    sql = f"""
        SELECT {_CAR_SELECT}, {_rental_count_expression()} AS rentalCount
        FROM Cars c
        LEFT JOIN CarTypes t ON t.typeId = c.TypeID
        {where}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, tuple(params) + (int(limit), int(offset)))
        return cursor.fetchall()
    finally:
        _close(cursor, connection)


def count_cars(keyword="", type_id=None, seats_min=None, seats_max=None,
               status=None):
    """Count cars matching the same filters as :func:`search_cars`."""
    where, params = _build_filters(keyword, type_id, seats_min, seats_max,
                                  status)
    sql = f"""
        SELECT COUNT(*) AS total
        FROM Cars c
        LEFT JOIN CarTypes t ON t.typeId = c.TypeID
        {where}
    """

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        return int(row["total"]) if row else 0
    finally:
        _close(cursor, connection)


def get_car_by_id(car_id):
    sql = f"""
        SELECT {_CAR_SELECT}, {_rental_count_expression()} AS rentalCount
        FROM Cars c
        LEFT JOIN CarTypes t ON t.typeId = c.TypeID
        WHERE c.carID = %s
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, (car_id,))
        return cursor.fetchone()
    finally:
        _close(cursor, connection)


def increment_views(car_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE Cars SET numberOfViews = numberOfViews + 1 WHERE carID = %s",
            (car_id,),
        )
        connection.commit()
        return cursor.rowcount == 1
    except Exception:
        connection.rollback()
        raise
    finally:
        _close(cursor, connection)


def get_car_types():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT typeId, typeName, description FROM CarTypes
               ORDER BY typeName"""
        )
        return cursor.fetchall()
    finally:
        _close(cursor, connection)
