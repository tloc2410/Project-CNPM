"""Only MySQL operations for password recovery; reuse the team's data.database."""
from data.database import get_db_connection


def find_user_by_id(user_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT UserID, email, passwordHash FROM users WHERE UserID = %s",
            (user_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def update_password_if_unchanged(user_id, previous_hash, new_hash):
    """Atomic update invalidates links tied to the previous password hash."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """UPDATE users SET passwordHash = %s
               WHERE UserID = %s AND passwordHash = %s""",
            (new_hash, user_id, previous_hash),
        )
        success = cursor.rowcount == 1
        connection.commit()
        return success
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
