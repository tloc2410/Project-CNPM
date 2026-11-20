
import pytest
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash
from business import auth_service
from flask import Flask
from itsdangerous.timed import TimestampSigner
from werkzeug.security import check_password_hash
from business import password_reset_service
@pytest.fixture

def mock_database(monkeypatch):
    users_by_email = {}
    users_by_phone = {}
    created_users = []

    def fake_find_email(email):
        return users_by_email.get(email)

    def fake_find_phone(phone):
        return users_by_phone.get(phone)

    def fake_create_user(full_name, phone, email, password_hash):
        user = {
            "UserID": len(created_users) + 1,
            "fullName": full_name,
            "phone": phone,
            "email": email,
            "passwordHash": password_hash,
            "isLocked": False,
            "role": "CUSTOMER",
        }
        created_users.append(user)
        users_by_email[email] = user
        users_by_phone[phone] = user
        return user["UserID"]

    monkeypatch.setattr(
        auth_service, "find_user_by_email", fake_find_email
    )
    monkeypatch.setattr(
        auth_service, "find_user_by_phone", fake_find_phone
    )
    monkeypatch.setattr(
        auth_service, "create_user", fake_create_user
    )

    return users_by_email, users_by_phone, created_users


def test_tc01_register_success(mock_database):
    emails, phones, created = mock_database

    success, message = auth_service.register_user(
        "Nguyen Van A",
        "0912345678",
        "user1@example.com",
        "Password@123",
    )

    assert success is True
    assert len(created) == 1
    assert created[0]["phone"] == "0912345678"
    assert "user1@example.com" in emails


def test_tc02_duplicate_email(mock_database):
    auth_service.register_user(
        "Nguyen Van A", "0912345678",
        "user1@example.com", "Password@123"
    )

    success, message = auth_service.register_user(
        "Nguyen Van B", "0987654321",
        "user1@example.com", "Password@123"
    )

    assert success is False
    assert "Email" in message


def test_tc03_duplicate_phone(mock_database):
    auth_service.register_user(
        "Nguyen Van A", "0912345678",
        "user1@example.com", "Password@123"
    )

    success, message = auth_service.register_user(
        "Nguyen Van B", "0912345678",
        "user2@example.com", "Password@123"
    )

    assert success is False
    assert "Số điện thoại" in message


def test_tc04_short_password(mock_database):
    success, message = auth_service.register_user(
        "Nguyen Van A",
        "0912345678",
        "user1@example.com",
        "12345",
    )

    assert success is False
    assert "8" in message


def test_tc05_invalid_phone(mock_database):
    success, message = auth_service.register_user(
        "Nguyen Van A",
        "123",
        "user1@example.com",
        "Password@123",
    )

    assert success is False
    assert "Số điện thoại" in message


def test_tc06_normalize_phone(mock_database):
    emails, phones, created = mock_database

    success, message = auth_service.register_user(
        "Nguyen Van A",
        "+84912345678",
        "user1@example.com",
        "Password@123",
    )

    assert success is True
    assert created[0]["phone"] == "0912345678"


def test_tc07_login_success(mock_database):
    auth_service.register_user(
        "Nguyen Van A",
        "0912345678",
        "user1@example.com",
        "Password@123",
    )

    success, message, user = auth_service.login_user(
        "user1@example.com", "Password@123"
    )

    assert success is True
    assert user is not None


def test_tc08_wrong_password(mock_database):
    auth_service.register_user(
        "Nguyen Van A",
        "0912345678",
        "user1@example.com",
        "Password@123",
    )

    success, message, user = auth_service.login_user(
        "user1@example.com", "WrongPassword"
    )

    assert success is False
    assert user is None


def test_tc09_email_not_found(mock_database):
    success, message, user = auth_service.login_user(
        "unknown@example.com", "Password@123"
    )

    assert success is False
    assert user is None


def test_tc10_locked_account(mock_database):
    emails, phones, created = mock_database

    auth_service.register_user(
        "Nguyen Van A",
        "0912345678",
        "user1@example.com",
        "Password@123",
    )

    emails["user1@example.com"]["isLocked"] = True

    success, message, user = auth_service.login_user(
        "user1@example.com", "Password@123"
    )

    assert success is False
    assert user is None
    assert "khóa" in message

@pytest.fixture
def reset_test_environment(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret-key-only"

    user = {
        "UserID": 1,
        "fullName": "Test User",
        "email": "reset@example.com",
        "phone": "0912345678",
        "passwordHash": generate_password_hash("OldPass@123"),
        "isLocked": False,
        "role": "CUSTOMER",
    }

    def fake_find_email(email):
        return user if email == user["email"] else None

    def fake_find_id(user_id):
        return user if user_id == user["UserID"] else None

    def fake_update_password(user_id, old_hash, new_hash):
        if user_id != user["UserID"]:
            return False
        if user["passwordHash"] != old_hash:
            return False
        user["passwordHash"] = new_hash
        return True

    monkeypatch.setattr(
        password_reset_service,
        "find_user_by_email",
        fake_find_email
    )
    monkeypatch.setattr(
        password_reset_service,
        "find_user_by_id",
        fake_find_id
    )
    monkeypatch.setattr(
        password_reset_service,
        "update_password_if_unchanged",
        fake_update_password
    )
    monkeypatch.setattr(
        auth_service,
        "find_user_by_email",
        fake_find_email
    )

    with app.app_context():
        yield user


def test_tc11_reset_password_success(reset_test_environment):
    user = reset_test_environment

    token = password_reset_service.create_token_for_email(
        user["email"]
    )

    success, message = password_reset_service.reset_password_with_token(
        token, "NewPass@12345", "NewPass@12345"
    )

    assert success is True
    assert check_password_hash(
        user["passwordHash"], "NewPass@12345"
    )


def test_tc12_expired_reset_token(reset_test_environment, monkeypatch):
    user = reset_test_environment

    token = password_reset_service.create_token_for_email(
        user["email"]
    )

    original_get_timestamp = TimestampSigner.get_timestamp

    def future_timestamp(self):
        return original_get_timestamp(self) + 16 * 60

    monkeypatch.setattr(
        TimestampSigner,
        "get_timestamp",
        future_timestamp
    )

    result = password_reset_service.verify_reset_token(token)

    assert result is None


def test_tc13_reset_token_cannot_be_reused(reset_test_environment):
    user = reset_test_environment

    token = password_reset_service.create_token_for_email(
        user["email"]
    )

    first_success, _ = password_reset_service.reset_password_with_token(
        token, "NewPass@12345", "NewPass@12345"
    )

    second_success, _ = password_reset_service.reset_password_with_token(
        token, "AnotherPass@12345", "AnotherPass@12345"
    )

    assert first_success is True
    assert second_success is False


def test_tc14_login_with_new_password(reset_test_environment):
    user = reset_test_environment

    token = password_reset_service.create_token_for_email(
        user["email"]
    )

    reset_success, _ = password_reset_service.reset_password_with_token(
        token, "NewPass@12345", "NewPass@12345"
    )

    success, message, logged_in_user = auth_service.login_user(
        user["email"], "NewPass@12345"
    )

    assert reset_success is True
    assert success is True
    assert logged_in_user is not None


def test_tc15_old_password_rejected(reset_test_environment):
    user = reset_test_environment

    token = password_reset_service.create_token_for_email(
        user["email"]
    )

    reset_success, _ = password_reset_service.reset_password_with_token(
        token, "NewPass@12345", "NewPass@12345"
    )

    success, message, logged_in_user = auth_service.login_user(
        user["email"], "OldPass@123"
    )

    assert reset_success is True
    assert success is False
    assert logged_in_user is None
