
from data.database import get_db_connection

try:
    connection = get_db_connection()

    print("Ket noi MySQL thanh cong!")

    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")

    print("Danh sach cac bang:")

    for table in cursor.fetchall():
        print(table[0])

    cursor.close()
    connection.close()

except Exception as error:
    print("Loi ket noi:", error)
