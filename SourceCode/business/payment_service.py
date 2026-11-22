"""Sandbox payment rules; no real charge, transfer or refund occurs."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from secrets import token_hex


class PaymentError(ValueError):
    pass


ONLINE_METHODS = frozenset(("E_WALLET",))
OFFLINE_METHODS = frozenset(("BANK_TRANSFER", "CASH"))
METHODS = ONLINE_METHODS | OFFLINE_METHODS


@dataclass(frozen=True)
class PaymentPlan:
    amount: Decimal
    status: str
    transaction_code: str
    paid_at: datetime | None


def plan_payment(method, order_id, total, deposit, demo_outcome="success", transfer_reference=None):
    """Build a demo payment; decline raises so the booking transaction rolls back."""
    if method not in METHODS:
        raise PaymentError("Invalid payment method.")
    if method in ONLINE_METHODS:
        if demo_outcome not in ("success", "declined"):
            raise PaymentError("Invalid test payment result.")
        if demo_outcome == "declined":
            raise PaymentError("Demo payment declined. No booking or charge was created.")
        return PaymentPlan(
            amount=Decimal(str(deposit)), status="Paid",
            transaction_code=f"DEMO-{order_id}-{token_hex(4).upper()}",
            paid_at=datetime.now(),
        )
    if method == "BANK_TRANSFER":
        return PaymentPlan(
            amount=Decimal(str(deposit)), status="Pending",
            transaction_code=transfer_reference or f"G12-{order_id}", paid_at=None,
        )
    return PaymentPlan(
        amount=Decimal(str(total)), status="Pending",
        transaction_code=f"CASH-{order_id}", paid_at=None,
    )


def balance_due(total, payment_status, payment_amount):
    paid = Decimal(str(payment_amount or 0)) if payment_status == "Paid" else Decimal("0")
    return max(Decimal("0"), Decimal(str(total or 0)) - paid)
