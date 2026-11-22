"""Admin validation and reports for Group12 Car Rental."""
# UML [Admin, Car, CarType, User, Order]: Admin role operations, not a Python Admin class.


from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from data import admin_repository as repo

CAR_STATUSES = ("available", "rented", "maintenance")
ORDER_TRANSITIONS = {
    "PENDING": {"CONFIRMED", "CANCELLED"},
    "NEW": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"RENTING", "CANCELLED"},
    "RENTING": {"RETURNED", "COMPLETED"},
    "RETURNED": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


class AdminError(ValueError):
    pass


def fleet():
    return repo.list_vehicles(), repo.list_vehicle_types()


def validate_vehicle(form):
    name = str(form.get("name") or "").strip()
    code = str(form.get("license_plate") or "").strip()
    status = str(form.get("status") or "available").strip().lower()
    if status == "under maintenance":
        status = "maintenance"
    description = str(form.get("description") or "").strip() if "description" in form else None
    try:
        seats = int(form.get("seats"))
        type_id = int(form.get("type_id"))
        price = Decimal(str(form.get("daily_price")))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise AdminError("Enter a valid vehicle type, seats and daily price.") from exc
    if not 2 <= len(name) <= 150 or not 1 <= len(code) <= 50:
        raise AdminError("Enter a vehicle name (2-150 chars) and code (1-50 chars).")
    if not 1 <= seats <= 55 or type_id <= 0 or not price.is_finite() or price <= 0:
        raise AdminError("Seats, vehicle type and price must be positive and valid.")
    if status not in CAR_STATUSES:
        raise AdminError("Invalid vehicle status.")
    if description is not None and len(description) > 2000:
        raise AdminError("Vehicle description is too long.")
    return {
        "name": name, "license_plate": code, "seats": seats,
        "type_id": type_id, "daily_price": price, "status": status,
        "description": description,
    }


# UML [Admin, Car]: addCar()/updateCar() use MySQL Cars.
def save_vehicle(form, vehicle_id=None):
    data = validate_vehicle(form)
    affected = (repo.edit_vehicle(vehicle_id, data) if vehicle_id is not None
                else repo.insert_vehicle(data))
    if not affected:
        raise AdminError("Vehicle was not found or could not be updated.")


def set_vehicle_status(vehicle_id, status):
    status = str(status or "").strip().lower()
    if status not in CAR_STATUSES:
        raise AdminError("Invalid vehicle status.")
    if not repo.change_vehicle_status(vehicle_id, status):
        raise AdminError("Vehicle not found.")


def delete_vehicle(vehicle_id):
    if not repo.remove_vehicle(vehicle_id):
        raise AdminError("Vehicle not found.")


def add_type(name, description):
    name = str(name or "").strip()
    description = str(description or "").strip()
    if not 2 <= len(name) <= 100:
        raise AdminError("Vehicle type name must have 2-100 characters.")
    if len(description) > 2000:
        raise AdminError("Vehicle type description is too long.")
    repo.insert_vehicle_type(name, description)


def delete_type(type_id):
    if not repo.remove_vehicle_type(type_id):
        raise AdminError("Vehicle type not found.")


def list_users():
    return repo.list_users()


# UML [Admin, User]: lockUser()/unlockUser() update Users.isLocked.
def change_user_lock(user_id, actor_id):
    if int(user_id) == int(actor_id):
        raise AdminError("You cannot lock or unlock your own Admin account.")
    target = next((u for u in repo.list_users() if int(u["id"]) == int(user_id)), None)
    if not target:
        raise AdminError("User not found.")
    locked = not bool(target.get("is_locked"))
    if locked and str(target.get("role") or "").upper() == "ADMIN":
        admins = [u for u in repo.list_users()
                  if str(u.get("role") or "").upper() == "ADMIN"
                  and not u.get("is_locked")]
        if len(admins) <= 1:
            raise AdminError("The last active Admin cannot be locked.")
    repo.set_user_lock(user_id, locked)
    return locked


def list_orders():
    return repo.list_orders()


# UML [Admin, Order]: confirmOrder()/updateOrderStatus() enforce allowed transitions.
def change_order_status(order_id, status):
    status = str(status or "").strip().upper()
    if status not in {v for group in ORDER_TRANSITIONS.values() for v in group}:
        raise AdminError("Invalid rental order status.")
    try:
        repo.update_order_status(order_id, status, ORDER_TRANSITIONS)
    except ValueError as exc:
        raise AdminError(str(exc)) from exc


def _day(value):
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def revenue_report():
    """Revenue is recorded Paid rows, not Pending or Refund Pending."""
    payments = repo.list_payments_for_reports()
    orders = repo.list_orders()
    now = date.today()
    daily = defaultdict(lambda: Decimal("0"))
    monthly = defaultdict(lambda: Decimal("0"))
    for p in payments:
        when = _day(p.get("paidAt"))
        if when:
            amount = Decimal(str(p.get("amount") or 0))
            daily[when.isoformat()] += amount
            monthly[when.strftime("%Y-%m")] += amount

    counts = defaultdict(lambda: {"completed": 0, "cancelled": 0})
    for o in orders:
        when = _day(o.get("order_time"))
        if not when:
            continue
        key = when.strftime("%Y-%m")
        status = str(o.get("status") or "").upper()
        if status in ("COMPLETED", "RETURNED"):
            counts[key]["completed"] += 1
        elif status == "CANCELLED":
            counts[key]["cancelled"] += 1
    months = sorted(set(monthly) | set(counts), reverse=True)[:12]
    return {
        "total_paid": sum(monthly.values(), Decimal("0")),
        "days": [
            {"label": (now - timedelta(days=i)).strftime("%d/%m"),
             "amount": daily[(now - timedelta(days=i)).isoformat()]}
            for i in range(6, -1, -1)
        ],
        "months": [
            {"month": m, "paid": monthly[m], **counts[m]} for m in months
        ],
    }
