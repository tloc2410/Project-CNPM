"""Two-stage rental collections: 30% deposit and remaining balance.

Customer QR scans and payment requests are never proof of money received.
Only a verified administrator may mark Pending collections as Paid.
All mutable actions lock the order row and use one database transaction.
"""
from datetime import datetime
from decimal import Decimal
from secrets import token_hex

from data import database, booking_repository as booking_repo
from data import payment_repository as payment_repo
from business import payment_service

SUPPORTED_BALANCE_METHODS = ("E_WALLET", "BANK_TRANSFER", "CASH")
INACTIVE_ORDER_STATUSES = ("CANCELLED", "CANCELED")
ZERO = Decimal("0")


class CollectionError(ValueError):
    """Safe business rule explanation for forms."""


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal("1"))


def payment_overview(order, payments):
    """Total only verified Paid rows; Pending is never counted as received.

    The schema permits multiple Payments per rental order. This works with both
    old single-payment orders and newly created deposit+balance records.
    """
    total = _money(order.get("totalPrice"))
    deposit = _money(order.get("deposit"))
    paid = sum((_money(p["amount"]) for p in payments
                if str(p.get("paymentStatus") or "").lower() == "paid"), ZERO)
    pending_rows = [p for p in payments
                    if str(p.get("paymentStatus") or "").lower() == "pending"]
    pending_amount = sum((_money(p["amount"]) for p in pending_rows), ZERO)
    balance = max(ZERO, total - paid)
    is_cancelled = str(order.get("status") or "").upper() in INACTIVE_ORDER_STATUSES
    latest_balance_request = next(
        (p for p in pending_rows
         if str(p.get("transactionCode") or "").startswith("BAL-")), None
    )
    if is_cancelled:
        state = "Cancelled"
    elif balance == ZERO:
        state = "Paid in Full"
    elif paid > ZERO:
        state = "Partially Paid"
    elif pending_rows:
        state = "Awaiting Verification"
    else:
        state = "Unpaid"
    return {
        "paid_amount": paid,
        "pending_amount": pending_amount,
        "balance_due": balance,
        "deposit_paid": paid >= deposit and total > ZERO,
        "payment_status": state,
        "pending_payment": pending_rows[0] if pending_rows else None,
        "pending_balance_request": latest_balance_request,
        "can_pay_remaining": (
            not is_cancelled and total > ZERO and balance > ZERO
            and paid >= deposit and not pending_rows
        ),
    }


def _read_customer_order(cursor, user_id, order_id, lock=False):
    if lock:
        order = booking_repo.get_order_for_update(cursor, order_id)
    else:
        cursor.execute(
            """SELECT oderID, useID, status, totalPrice, deposit, paymentMethod
               FROM Orders WHERE oderID = %s""", (order_id,),
        )
        order = cursor.fetchone()
    if not order or order["useID"] != user_id:
        raise CollectionError("Rental order not found.")
    return order


def request_remaining_payment(user_id, order_id, method):
    """Submit a request for the exact outstanding amount (Pending, not Paid).

    Multiple tabs/requests cannot create duplicate outstanding collections:
    transaction lock on Orders serializes changes with admin confirmation.
    """
    if method not in SUPPORTED_BALANCE_METHODS:
        raise CollectionError("Please select a valid remaining payment method.")
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        order = _read_customer_order(cursor, user_id, order_id, lock=True)
        payments = payment_repo.list_payments_for_orders(cursor, [order_id])
        overview = payment_overview(order, payments)
        if not overview["can_pay_remaining"]:
            raise CollectionError(
                "The deposit must be verified first, or another payment request is awaiting verification."
            )
        amount = overview["balance_due"]
        reference = f"BAL-{order_id}-{token_hex(5).upper()}"
        payment_id = payment_repo.insert_payment(
            cursor, order_id, amount, method, "Pending", reference
        )
        conn.commit()
        return payment_id
    except CollectionError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise CollectionError("Unable to create payment request. Please try again.") from exc
    finally:
        cursor.close()
        conn.close()


def cancel_remaining_request(user_id, order_id):
    """Let the owner cancel an unverified remaining request and choose again."""
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        order = _read_customer_order(cursor, user_id, order_id, lock=True)
        if str(order.get("status") or "").upper() in INACTIVE_ORDER_STATUSES:
            raise CollectionError("This order has been cancelled.")
        payments = payment_repo.list_payments_for_orders(cursor, [order_id])
        request = payment_overview(order, payments)["pending_balance_request"]
        if not request:
            raise CollectionError("There is no pending remaining payment to cancel.")
        changed = payment_repo.update_payment_status(cursor, request["paymentID"], "Cancelled")
        if not changed:
            raise CollectionError("Payment request could not be cancelled.")
        conn.commit()
        return True
    except CollectionError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise CollectionError("Unable to cancel this payment request.") from exc
    finally:
        cursor.close()
        conn.close()


def is_active_admin(user_id):
    if not user_id:
        return False
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT role, isLocked FROM Users WHERE UserID = %s", (user_id,)
        )
        row = cursor.fetchone()
        return bool(row and str(row.get("role") or "").upper() == "ADMIN"
                    and not row.get("isLocked"))
    finally:
        cursor.close()
        conn.close()


def list_pending_collections():
    """Admin-only caller: pending deposit, full cash or remaining payments."""
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return payment_repo.list_pending_collections(cursor)
    finally:
        cursor.close()
        conn.close()


def confirm_collection(payment_id):
    """Record an ADMIN-verified received payment exactly once.

    Caller must already have verified Admin authorization. This does NOT query
    MoMo/bank; staff must independently verify actual receipt first.
    """
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        # Read the order id first, then lock order before locking payment row.
        # Consistent lock ordering prevents races with balance-request creation.
        cursor.execute(
            "SELECT oderID FROM Payments WHERE paymentID = %s", (payment_id,)
        )
        pointer = cursor.fetchone()
        if not pointer:
            raise CollectionError("Payment not found.")
        order_id = pointer["oderID"]
        order = booking_repo.get_order_for_update(cursor, order_id)
        if not order:
            raise CollectionError("Rental order not found.")
        if str(order.get("status") or "").upper() in INACTIVE_ORDER_STATUSES:
            raise CollectionError("Cannot confirm payment for a cancelled order.")
        payments = payment_repo.list_payments_for_orders(cursor, [order_id])
        payment = next((p for p in payments if p["paymentID"] == payment_id), None)
        if not payment or str(payment.get("paymentStatus") or "") != "Pending":
            raise CollectionError("This payment is not Pending or was already confirmed.")

        overview = payment_overview(order, payments)
        if _money(payment["amount"]) <= ZERO or (
            overview["paid_amount"] + _money(payment["amount"])
            > _money(order["totalPrice"])
        ):
            raise CollectionError("Payment amount exceeds the outstanding order total.")

        if not payment_repo.mark_payment_paid(cursor, payment_id, datetime.now()):
            raise CollectionError("This payment was already processed.")
        # Once staff verifies the required deposit, the reservation can move
        # from pending to confirmed. Do not overwrite Renting/Completed states.
        verified_total = overview["paid_amount"] + _money(payment["amount"])
        if (str(order.get("status") or "").upper() in ("PENDING", "NEW")
                and verified_total >= _money(order.get("deposit"))):
            booking_repo.update_order_status(cursor, order_id, "CONFIRMED")
        conn.commit()
        return order_id
    except CollectionError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise CollectionError("Failed to confirm payment. No change was committed.") from exc
    finally:
        cursor.close()
        conn.close()
