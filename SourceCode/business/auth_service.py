# UML [User]: register()/login() logic; Users records stand in for a Python User class.
import re
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from data.user_repository import (
    find_user_by_email,
    find_user_by_phone,
    create_user
)

def register_user(full_name, phone, email, password):
    full_name = full_name.strip()
    email = email.strip().lower()

    phone = re.sub(r"[\s().-]", "", phone.strip())

    if phone.startswith("+84"):
        phone = "0" + phone[3:]

    if not full_name or not phone or not email or not password:
        return False, "Vui lòng nhập đầy đủ thông tin."

    if not re.fullmatch(r"0[35789][0-9]{8}", phone):
        return False, "Số điện thoại không hợp lệ."

    if len(password) < 8:
        return False, "Mật khẩu phải có ít nhất 8 ký tự."

    if find_user_by_email(email):
        return False, "Email này đã được đăng ký."

    if find_user_by_phone(phone):
        return False, "Số điện thoại này đã được đăng ký."

    password_hash = generate_password_hash(password)

    try:
        user_id = create_user(
            full_name, phone, email, password_hash
        )
    except IntegrityError:
        return False, "Email hoặc số điện thoại đã được đăng ký."

    return True, f"Đăng ký thành công! Mã tài khoản: {user_id}"

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