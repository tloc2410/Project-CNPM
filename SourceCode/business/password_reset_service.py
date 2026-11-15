"""Password reset business logic: signed 15-minute, single-use links.

Tokens contain only the user ID and a keyed fingerprint of the current
password hash. After a successful password change, the old token is invalid.
No extra database table is required for this implementation.
"""
import hashlib
import hmac

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

from data.user_repository import find_user_by_email
from data.password_reset_repository import find_user_by_id, update_password_if_unchanged

TOKEN_LIFETIME_SECONDS = 15 * 60
TOKEN_SALT = "group12-password-reset-v1"


def _serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt=TOKEN_SALT)


def _password_fingerprint(password_hash):
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hmac.new(key, password_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token_for_email(email):
    """Return a reset token, or None when the email is not registered."""
    email = (email or "").strip().lower()
    if not email:
        return None

    user = find_user_by_email(email)
    if user is None:
        return None

    return _serializer().dumps({
        "uid": user["UserID"],
        "fp": _password_fingerprint(user["passwordHash"]),
    })


def verify_reset_token(token):
    """Return the current user for a valid link; otherwise return None."""
    try:
        data = _serializer().loads(token, max_age=TOKEN_LIFETIME_SECONDS)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None
    user_id = data.get("uid")
    fingerprint = data.get("fp")
    if not isinstance(user_id, int) or not isinstance(fingerprint, str):
        return None

    user = find_user_by_id(user_id)
    if not user:
        return None
    if not hmac.compare_digest(
        _password_fingerprint(user["passwordHash"]), fingerprint
    ):
        return None
    return user


def reset_password_with_token(token, password, confirm_password):
    """Validate the link and save the new password hash atomically."""
    user = verify_reset_token(token)
    if user is None:
        return False, "This reset link is invalid, expired, or already used."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    if password != confirm_password:
        return False, "Passwords do not match."

    new_hash = generate_password_hash(password)
    updated = update_password_if_unchanged(
        user["UserID"], user["passwordHash"], new_hash
    )
    if not updated:
        return False, "This reset link is invalid, expired, or already used."

    return True, "Password updated successfully. You can now log in."
