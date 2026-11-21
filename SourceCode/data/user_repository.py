

from data.database import get_db_connection


def find_user_by_email(email):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        sql = "SELECT * FROM users WHERE email = %s"
        cursor.execute(sql, (email,))
        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

def find_user_by_phone(phone):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM users WHERE phone = %s",
            (phone,)
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def find_user_permissions(user_id):
    """Return the current role/lock state from MySQL for backend auth checks."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT role, isLocked FROM users WHERE UserID = %s",
            (user_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def create_user(full_name, phone, email, password_hash):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        sql = """
            INSERT INTO users (fullName, phone, email, passwordHash)
            VALUES (%s, %s, %s, %s)
        """

        cursor.execute(
            sql,
            (full_name, phone, email, password_hash)
        )

        connection.commit()
        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def update_user_profile(user_id, full_name, phone, address):
    """Update the current user's name, phone and address, not their role/email."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT UserID FROM Users WHERE phone = %s AND UserID <> %s",
            (phone, user_id),
        )
        if cursor.fetchone():
            return False, "Số điện thoại đã được tài khoản khác sử dụng."
        cursor.execute(
            """UPDATE Users
               SET fullName = %s, phone = %s, address = %s
               WHERE UserID = %s""",
            (full_name, phone, address, user_id),
        )
        changed = cursor.rowcount
        connection.commit()
        return (True, "Cập nhật thông tin tài khoản thành công.") if changed else (
            False, "Không tìm thấy tài khoản để cập nhật."
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
