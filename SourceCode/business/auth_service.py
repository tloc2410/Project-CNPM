
from werkzeug.security import generate_password_hash
from data.user_repository import (
    find_user_by_email,
    create_user
)


def register_user(full_name, email, password):
    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name or not email or not password:
        return False, "Vui lòng nhập đầy đủ thông tin."

    if len(password) < 8:
        return False, "Mật khẩu phải có ít nhất 8 ký tự."

    if find_user_by_email(email):
        return False, "Email này đã được đăng ký."

    password_hash = generate_password_hash(password)

    user_id = create_user(
        full_name,
        email,
        password_hash
    )

    return True, f"Đăng ký thành công! Mã tài khoản: {user_id}"
from werkzeug.security import check_password_hash

def login_user(email, password):
    email = email.strip().lower()

    user = find_user_by_email(email)

    if not user:
        return False, "Email hoặc mật khẩu không đúng.", None

    if user["isLocked"]:
        return False, "Tài khoản đã bị khóa.", None

    if not check_password_hash(user["passwordHash"], password):
        return False, "Email hoặc mật khẩu không đúng.", None

    return True, "Đăng nhập thành công!", user