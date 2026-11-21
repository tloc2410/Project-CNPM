

from data import database


def find_user_by_email(email):
    connection = database.get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        sql = "SELECT * FROM users WHERE email = %s"
        cursor.execute(sql, (email,))
        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

def find_user_by_phone(phone):
    connection = database.get_db_connection()
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
    connection = database.get_db_connection()
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
    connection = database.get_db_connection()
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
    connection = database.get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT UserID FROM Users WHERE phone = %s AND UserID <> %s",
            (phone, user_id),
        )
        if cursor.fetchone():
            return False, "This phone number is already used by another account."
        cursor.execute(
            """UPDATE Users
               SET fullName = %s, phone = %s, address = %s
               WHERE UserID = %s""",
            (full_name, phone, address, user_id),
        )
        changed = cursor.rowcount
        connection.commit()
        return (True, "Your profile has been updated successfully.") if changed else (
            False, "Account not found. No changes were saved."
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
