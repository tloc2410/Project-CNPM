

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


def create_user(full_name, email, password_hash):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        sql = """
            INSERT INTO users (fullName, email, passwordHash)
            VALUES (%s, %s, %s)
        """

        cursor.execute(sql, (full_name, email, password_hash))
        connection.commit()

        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
