"""QR display only; receipt needs provider verification or staff reconciliation."""
import os
import re
from urllib.parse import urlencode


def bank_transfer_qr(amount, reference):
    """Create a VietQR link only for a configured, valid recipient."""
    bank = os.getenv("PAYMENT_BANK_BIN", "").strip()
    account = os.getenv("PAYMENT_BANK_ACCOUNT", "").strip()
    holder = os.getenv("PAYMENT_BANK_HOLDER", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{2,12}", bank):
        return None
    if not re.fullmatch(r"[A-Za-z0-9]{5,32}", account):
        return None
    if not re.fullmatch(r"[A-Za-z0-9-]{3,40}", reference or ""):
        return None
    try:
        amount_int = int(amount)
    except (TypeError, ValueError):
        return None
    if amount_int <= 0:
        return None
    query = {"amount": str(amount_int), "addInfo": reference}
    if holder:
        query["accountName"] = holder[:100]
    return (
        f"https://img.vietqr.io/image/{bank}-{account}-compact2.png?"
        + urlencode(query)
    )


def momo_merchant_qr_filename():
    """Validate the configured merchant QR image filename."""
    name = os.getenv("MOMO_MERCHANT_QR_FILENAME", "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,90}\.(png|jpg|jpeg|webp)", name, re.I):
        return None
    return name
