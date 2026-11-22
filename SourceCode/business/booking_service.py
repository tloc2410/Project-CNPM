"""Business logic layer for module Rental Cart & Booking (Do Thu Thao).

Responsibilities:
- Pure cart state manipulation (add, remove, bulk remove, selection toggle,
  date & location updates, rental-days stepping).
- Date validation, anti-overlap calendar checks against MySQL, and automatic
  fee calculation (line totals, subtotal, delivery fee with >= 2,000,000 VND
  free-delivery rule, 30% deposit, grand total).
- Atomic transactional order placement (Orders + Oderitem) and cancellation
  with strict ROLLBACK on any business or database error.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from data import booking_repository as repo
from data import database
from data import payment_repository
from business import payment_service

ORDER_STATUS_PENDING = "PENDING"
ORDER_STATUS_CANCELLED = "CANCELLED"
CANCELLABLE_STATUSES = ("PENDING", "NEW", "CONFIRMED")

FREE_DELIVERY_THRESHOLD = Decimal("2000000")
STANDARD_DELIVERY_FEE = Decimal("100000")

RECEIVING_METHODS = {
    "PICKUP": Decimal("0"),               # Nhận xe tại cửa hàng / điểm hẹn
    "DELIVERY": STANDARD_DELIVERY_FEE,    # Giao xe tận nơi (miễn phí từ 2.000.000đ)
}

PAYMENT_METHODS = ("CARD", "E_WALLET", "BANK_TRANSFER", "CASH")

PAYMENT_METHOD_LABELS = {
    "CARD": "Credit / Debit Card",
    "E_WALLET": "E-Wallet",
    "BANK_TRANSFER": "Bank Transfer",
    "CASH": "Cash on Delivery",
}

RECEIVING_METHOD_LABELS = {
    "PICKUP": "Nhận xe tại điểm hẹn / cửa hàng",
    "DELIVERY": "Giao xe tận nơi",
}

LOCATIONS = (
    "Tan Son Nhat Airport",
    "Group 12 Showroom - District 1",
    "Noi Bai Airport",
    "Da Nang Airport",
    "Home Delivery",
)

SHOWROOM_LOCATION = "Group 12 Showroom - District 1"
DEFAULT_LOCATION = "Tan Son Nhat Airport"
DEPOSIT_RATE = Decimal("0.30")
MAX_RENTAL_DAYS = 60


class BookingError(Exception):
    """Business rule violation whose message can be shown safely to the user."""


# ---------------------------------------------------------------- helpers
def _money(value):
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def default_rental_dates(today=None):
    """Return sensible default (pickup_str, return_str) = (tomorrow, +2 days)."""
    base = today or date.today()
    pickup = base + timedelta(days=1)
    return_ = pickup + timedelta(days=1)
    return pickup.isoformat(), return_.isoformat()


def validate_dates(pickup, return_, today=None):
    """Return (ok, message, rental_days)."""
    today = today or date.today()
    p, r = parse_date(pickup), parse_date(return_)
    if p is None or r is None:
        return False, "Vui lòng chọn đầy đủ ngày nhận xe và ngày trả xe.", 0
    if p < today:
        return False, "Ngày nhận xe không được ở trong quá khứ.", 0
    if r <= p:
        return False, "Ngày trả xe phải sau ngày nhận xe ít nhất 1 ngày.", 0
    days = (r - p).days
    if days > MAX_RENTAL_DAYS:
        return False, f"Chỉ được thuê tối đa {MAX_RENTAL_DAYS} ngày.", 0
    return True, "", days


def calculate_line_total(price_per_day, rental_days):
    if int(rental_days) <= 0:
        return Decimal("0")
    return _money(Decimal(str(price_per_day)) * int(rental_days))


def calculate_delivery_fee(subtotal, receiving_method="PICKUP"):
    subtotal = _money(subtotal)
    if subtotal <= 0 or receiving_method != "DELIVERY":
        return Decimal("0")
    if subtotal >= FREE_DELIVERY_THRESHOLD:
        return Decimal("0")
    return STANDARD_DELIVERY_FEE


def calculate_totals(line_totals, receiving_method="PICKUP"):
    subtotal = _money(sum((Decimal(x) for x in line_totals), Decimal("0")))
    delivery_fee = calculate_delivery_fee(subtotal, receiving_method)
    total = _money(subtotal + delivery_fee)
    deposit = _money(total * DEPOSIT_RATE)
    return {
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total,
        "deposit": deposit,
    }


def _overlap_message(car, clashes):
    c = clashes[0]
    return (
        f"Xe {car['name']} đã có đơn đặt trùng lịch từ {c['pickupDate']} "
        f"đến {c['returnDate']}. Vui lòng chọn khoảng thời gian khác."
    )


def _normalize_cart_item(item):
    return {
        "car_id": int(item["car_id"]),
        "pickup_date": (item.get("pickup_date") or "").strip(),
        "return_date": (item.get("return_date") or "").strip(),
        "selected": bool(item.get("selected", True)),
        "pickup_location": (item.get("pickup_location") or DEFAULT_LOCATION).strip(),
        "return_location": (item.get("return_location") or DEFAULT_LOCATION).strip(),
    }


# ---------------------------------------------------------------- cart (pure)
def add_to_cart(
    cart,
    car_id,
    pickup_date="",
    return_date="",
    selected=True,
    pickup_location=DEFAULT_LOCATION,
    return_location=DEFAULT_LOCATION,
):
    cart = [_normalize_cart_item(i) for i in (cart or [])]
    car_id = int(car_id)
    if any(item["car_id"] == car_id for item in cart):
        return cart, False, "Xe này đã có trong giỏ hàng."
    cart.append(
        {
            "car_id": car_id,
            "pickup_date": (pickup_date or "").strip(),
            "return_date": (return_date or "").strip(),
            "selected": bool(selected),
            "pickup_location": (pickup_location or DEFAULT_LOCATION).strip(),
            "return_location": (return_location or DEFAULT_LOCATION).strip(),
        }
    )
    return cart, True, "Đã thêm xe vào giỏ hàng."


def select_only_cart_item(cart, car_id):
    """For Book Now, select the requested car while preserving other cart items."""
    car_id = int(car_id)
    items = [_normalize_cart_item(item) for item in (cart or [])]
    for item in items:
        item["selected"] = item["car_id"] == car_id
    return items


def remove_from_cart(cart, car_id):
    car_id = int(car_id)
    items = [_normalize_cart_item(i) for i in (cart or [])]
    new_cart = [item for item in items if item["car_id"] != car_id]
    return new_cart, len(new_cart) != len(items)


def remove_selected_from_cart(cart):
    items = [_normalize_cart_item(i) for i in (cart or [])]
    new_cart = [item for item in items if not item["selected"]]
    removed_count = len(items) - len(new_cart)
    return new_cart, removed_count


def remove_car_ids_from_cart(cart, car_ids):
    to_remove = {int(cid) for cid in (car_ids or [])}
    items = [_normalize_cart_item(i) for i in (cart or [])]
    return [item for item in items if item["car_id"] not in to_remove]


def update_cart_dates(cart, car_id, pickup, return_):
    car_id = int(car_id)
    items = [_normalize_cart_item(i) for i in (cart or [])]
    for item in items:
        if item["car_id"] == car_id:
            item["pickup_date"] = (pickup or "").strip()
            item["return_date"] = (return_ or "").strip()
    return items


def update_cart_locations(cart, car_id, pickup_location, return_location):
    car_id = int(car_id)
    items = [_normalize_cart_item(i) for i in (cart or [])]
    for item in items:
        if item["car_id"] == car_id:
            if pickup_location:
                item["pickup_location"] = pickup_location.strip()
            if return_location:
                item["return_location"] = return_location.strip()
    return items


def update_all_selected_dates(cart, pickup, return_, pickup_location=None, return_location=None):
    """Apply date/location edits from the Checkout form to all selected cart items."""
    items = [_normalize_cart_item(i) for i in (cart or [])]
    for item in items:
        if item["selected"]:
            if pickup is not None:
                item["pickup_date"] = (pickup or "").strip()
            if return_ is not None:
                item["return_date"] = (return_ or "").strip()
            if pickup_location:
                item["pickup_location"] = pickup_location.strip()
            if return_location:
                item["return_location"] = return_location.strip()
    return items


def set_item_selected(cart, car_id, selected):
    car_id = int(car_id)
    items = [_normalize_cart_item(i) for i in (cart or [])]
    for item in items:
        if item["car_id"] == car_id:
            item["selected"] = bool(selected)
    return items


def set_all_selected(cart, selected):
    items = [_normalize_cart_item(i) for i in (cart or [])]
    for item in items:
        item["selected"] = bool(selected)
    return items


def get_selected_cart_items(cart):
    return [i for i in (_normalize_cart_item(x) for x in (cart or [])) if i["selected"]]


# ---------------------------------------------------------------- DB reads
def get_available_cars(keyword=""):
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return repo.list_available_cars(cursor, keyword=keyword)
    finally:
        cursor.close()
        conn.close()


def get_renter_profile(user_id):
    if not user_id:
        return None
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return repo.get_user_by_id(cursor, user_id)
    finally:
        cursor.close()
        conn.close()


def build_cart_summary(cart, receiving_method="PICKUP", today=None, selected_only=False):
    """Load cars from DB, validate dates, check overlaps, and compute totals.

    Totals are always computed from selected items (so the Cart page Order
    Summary reflects the checkboxes just like the Figma design).
    """
    normalized = [_normalize_cart_item(i) for i in (cart or [])]
    if selected_only:
        normalized = [i for i in normalized if i["selected"]]

    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cars = repo.get_cars_by_ids(cursor, [i["car_id"] for i in normalized])
        items = []
        selected_line_totals = []

        for item in normalized:
            car = cars.get(item["car_id"])
            row = {
                "car_id": item["car_id"],
                "pickup_date": item["pickup_date"],
                "return_date": item["return_date"],
                "selected": item["selected"],
                "pickup_location": item["pickup_location"],
                "return_location": item["return_location"],
                "car": car,
                "rental_days": 0,
                "line_total": Decimal("0"),
                "error": "",
                "overlap_conflict": False,
            }
            if car is None:
                row["error"] = "Xe không còn tồn tại trong hệ thống."
                items.append(row)
                continue

            if str(car.get("status", "")).lower() not in ("available", ""):
                row["error"] = f"Xe {car['name']} hiện không ở trạng thái sẵn sàng cho thuê."
                items.append(row)
                continue

            ok, msg, days = validate_dates(row["pickup_date"], row["return_date"], today)
            if not ok:
                row["error"] = msg
            else:
                p_date = parse_date(row["pickup_date"])
                r_date = parse_date(row["return_date"])
                clashes = repo.find_overlapping_bookings(
                    cursor, car["carID"], p_date, r_date
                )
                row["rental_days"] = days
                row["line_total"] = calculate_line_total(car["pricePerDay"], days)
                if clashes:
                    row["error"] = _overlap_message(car, clashes)
                    row["overlap_conflict"] = True
                if row["selected"]:
                    selected_line_totals.append(row["line_total"])

            items.append(row)

        selected_items = [i for i in items if i["selected"]]
        totals = calculate_totals(selected_line_totals, receiving_method)
        all_selected = bool(items) and all(i["selected"] for i in items)
        is_valid = bool(selected_items) and all(not i["error"] for i in selected_items)

        return {
            "items": items,
            "selected_count": len(selected_items),
            "total_count": len(items),
            "all_selected": all_selected,
            **totals,
            "is_valid": is_valid,
            "receiving_method": receiving_method,
        }
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------- transactions
def place_order(
    user_id,
    cart,
    receiving_method="PICKUP",
    payment_method="CARD",
    today=None,
    now=None,
    demo_outcome="success",
):
    """Create Orders + Oderitem + Payments in ONE atomic database transaction.

    - Locks requested car rows (SELECT ... FOR UPDATE).
    - Re-verifies car availability and checks overlapping active orders.
    - Computes authoritative totals from DB prices.
    - Commits only if Orders + all Oderitem inserts succeed.
    - Executes ROLLBACK on ANY error so no partial/corrupt rows are persisted.

    Returns the newly created ``oderID``.
    Raises ``BookingError`` on business or database failure.
    """
    if not user_id:
        raise BookingError("Vui lòng đăng nhập để đặt xe.")

    items = [_normalize_cart_item(i) for i in (cart or []) if i.get("selected", True)]
    if not items:
        raise BookingError("Vui lòng chọn ít nhất một xe trong giỏ hàng để đặt.")

    if receiving_method not in RECEIVING_METHODS:
        raise BookingError("Phương thức nhận xe không hợp lệ.")
    if payment_method not in PAYMENT_METHODS:
        raise BookingError("Phương thức thanh toán không hợp lệ.")

    # Validate dates and prevent duplicate car IDs before starting DB transaction.
    seen_car_ids = set()
    parsed = []
    for item in items:
        cid = item["car_id"]
        if cid in seen_car_ids:
            raise BookingError("Giỏ hàng có xe bị trùng lặp. Vui lòng kiểm tra lại.")
        seen_car_ids.add(cid)

        ok, msg, days = validate_dates(item["pickup_date"], item["return_date"], today)
        if not ok:
            raise BookingError(msg)
        parsed.append((cid, parse_date(item["pickup_date"]), parse_date(item["return_date"]), days))

    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()

        # Lock car rows to prevent race-condition double booking.
        cars = repo.get_cars_by_ids(cursor, [p[0] for p in parsed], lock=True)

        line_totals = []
        for car_id, p_date, r_date, days in parsed:
            car = cars.get(car_id)
            if car is None:
                raise BookingError("Có xe trong giỏ hàng không còn tồn tại.")
            if str(car.get("status", "")).lower() not in ("available", ""):
                raise BookingError(f"Xe {car['name']} hiện không ở trạng thái cho thuê.")

            clashes = repo.find_overlapping_bookings(cursor, car_id, p_date, r_date)
            if clashes:
                raise BookingError(_overlap_message(car, clashes))

            line_totals.append(calculate_line_total(car["pricePerDay"], days))

        totals = calculate_totals(line_totals, receiving_method)
        order_id = repo.insert_order(
            cursor,
            user_id=user_id,
            order_time=now or datetime.now(),
            status=ORDER_STATUS_PENDING,
            receiving_method=receiving_method,
            delivery_fee=totals["delivery_fee"],
            deposit=totals["deposit"],
            total_price=totals["total"],
            payment_method=payment_method,
        )

        for car_id, p_date, r_date, days in parsed:
            repo.insert_order_item(
                cursor,
                order_id=order_id,
                car_id=car_id,
                unit_price=cars[car_id]["pricePerDay"],
                rental_days=days,
                pickup_date=p_date,
                return_date=r_date,
            )

        # Record the payment in the SAME transaction. No independent commit:
        # a declined demo or DB failure rolls back the entire rental order.
        plan = payment_service.plan_payment(
            payment_method, order_id, totals["total"], totals["deposit"], demo_outcome
        )
        payment_repository.insert_payment(
            cursor, order_id, plan.amount, payment_method, plan.status,
            plan.transaction_code, plan.paid_at,
        )
        conn.commit()
        return order_id
    except payment_service.PaymentError as exc:
        conn.rollback()
        raise BookingError(str(exc)) from exc
    except BookingError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise BookingError(
            "Đặt xe thất bại do lỗi hệ thống, giao dịch đã được hoàn tác (ROLLBACK). Vui lòng thử lại."
        ) from exc
    finally:
        cursor.close()
        conn.close()


def cancel_order(user_id, order_id):
    """Cancel an order belonging to ``user_id`` inside a database transaction."""
    if not user_id:
        raise BookingError("Vui lòng đăng nhập để hủy đơn hàng.")

    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        order = repo.get_order_for_update(cursor, order_id)
        if order is None or order["useID"] != user_id:
            raise BookingError("Không tìm thấy đơn hàng.")
        if (order["status"] or "").upper() not in CANCELLABLE_STATUSES:
            raise BookingError("Đơn hàng này không thể hủy ở trạng thái hiện tại.")

        repo.update_order_status(cursor, order_id, ORDER_STATUS_CANCELLED)
        payment = payment_repository.latest_payment_for_update(cursor, order_id)
        if payment:
            previous = str(payment.get("paymentStatus") or "")
            if previous == "Paid":
                # Sandbox-only: status update, not a real gateway refund.
                payment_repository.update_payment_status(
                    cursor, payment["paymentID"], "Refunded"
                )
            elif previous == "Pending":
                payment_repository.update_payment_status(
                    cursor, payment["paymentID"], "Cancelled"
                )
        conn.commit()
        return True
    except BookingError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise BookingError("Hủy đơn thất bại, giao dịch đã được hoàn tác. Vui lòng thử lại.") from exc
    finally:
        cursor.close()
        conn.close()


def get_user_orders(user_id):
    """Return a customer's orders with nested Oderitem records."""
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        orders = repo.list_orders_by_user(cursor, user_id)
        order_ids = [o["oderID"] for o in orders]
        items = repo.list_items_by_order_ids(cursor, order_ids)
        payments = payment_repository.list_payments_for_orders(cursor, order_ids)
        latest = {}
        for row in payments:
            latest.setdefault(row["oderID"], row)
        for order in orders:
            order_items = [i for i in items if i["OderID"] == order["oderID"]]
            for oi in order_items:
                oi["lineTotal"] = calculate_line_total(
                    oi.get("unitPrice") or 0, oi.get("rentalDays") or 0
                )
            order["items"] = order_items
            order["payment"] = latest.get(order["oderID"])
            order["payment_status"] = (
                order["payment"]["paymentStatus"] if order["payment"] else "Not recorded"
            )
            order["payment_amount"] = (
                order["payment"]["amount"] if order["payment"] else Decimal("0")
            )
            order["balance_due"] = payment_service.balance_due(
                order["totalPrice"], order["payment_status"], order["payment_amount"]
            )
            order["can_cancel"] = (order["status"] or "").upper() in CANCELLABLE_STATUSES
            order["payment_label"] = PAYMENT_METHOD_LABELS.get(
                order.get("paymentMethod"), order.get("paymentMethod") or ""
            )
            order["receiving_label"] = RECEIVING_METHOD_LABELS.get(
                order.get("receivingMethod"), order.get("receivingMethod") or ""
            )
        return orders
    finally:
        cursor.close()
        conn.close()



def get_order_payment_details(user_id, order_id):
    """Return only the signed-in customer's order and payment receipt."""
    if not user_id:
        raise BookingError("Please sign in to view a payment.")
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        orders = repo.list_orders_by_user(cursor, user_id)
        order = next((o for o in orders if o["oderID"] == order_id), None)
        if not order:
            raise BookingError("Order not found.")
        order["items"] = repo.list_items_by_order_ids(cursor, [order_id])
        payments = payment_repository.list_payments_for_orders(cursor, [order_id])
        order["payment"] = payments[0] if payments else None
        order["payment_status"] = (
            order["payment"]["paymentStatus"] if order["payment"] else "Not recorded"
        )
        order["payment_amount"] = (
            order["payment"]["amount"] if order["payment"] else Decimal("0")
        )
        order["balance_due"] = payment_service.balance_due(
            order["totalPrice"], order["payment_status"], order["payment_amount"]
        )
        order["payment_label"] = PAYMENT_METHOD_LABELS.get(
            order["paymentMethod"], order["paymentMethod"]
        )
        return order
    finally:
        cursor.close()
        conn.close()
