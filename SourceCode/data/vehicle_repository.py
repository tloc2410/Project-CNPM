from data.database import get_db_connection


def get_all_vehicle_types():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT typeId AS id,
                   typeName AS name,
                   description
            FROM cartypes
            ORDER BY typeId ASC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def create_vehicle_type(name, description=""):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cartypes (typeName, description)
            VALUES (%s, %s)
            """,
            (name, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def delete_vehicle_type(type_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cartypes WHERE typeId = %s", (type_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def get_all_vehicles():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT c.carID AS id,
                   c.code AS license_plate,
                   c.name,
                   c.TypeID AS type_id,
                   ct.typeName AS type_name,
                   c.numberOfSeats AS seats,
                   c.pricePerDay AS daily_price,
                   c.status,
                   c.description,
                   c.pictures,
                   c.numberOfViews
            FROM cars c
            LEFT JOIN cartypes ct ON c.TypeID = ct.typeId
            ORDER BY c.carID DESC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def create_vehicle(
    name,
    license_plate,
    type_id,
    daily_price,
    status="Available",
    seats=4,
    description="",
    pictures="",
):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cars (
                TypeID,
                code,
                name,
                pictures,
                description,
                numberOfSeats,
                pricePerDay,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                type_id,
                license_plate,
                name,
                pictures,
                description,
                seats,
                daily_price,
                status,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def update_vehicle(
    vehicle_id,
    name,
    license_plate,
    type_id,
    daily_price,
    status,
    seats=4,
    description="",
):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE cars
            SET TypeID = %s,
                code = %s,
                name = %s,
                numberOfSeats = %s,
                pricePerDay = %s,
                status = %s,
                description = %s
            WHERE carID = %s
            """,
            (
                type_id,
                license_plate,
                name,
                seats,
                daily_price,
                status,
                description,
                vehicle_id,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def update_vehicle_status(vehicle_id, new_status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cars SET status = %s WHERE carID = %s",
            (new_status, vehicle_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def delete_vehicle(vehicle_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cars WHERE carID = %s", (vehicle_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()