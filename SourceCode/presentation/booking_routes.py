"""Flask routes for rental cart, checkout, payments and orders."""

from datetime import datetime
from functools import wraps
import os
import secrets
import time

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from business import booking_service as svc
from business import payment_qr
from business import payment_collection_service as collection_service

booking_bp = Blueprint("booking", __name__)

CART_KEY = "rental_cart"
DIRECT_BOOKING_KEY = "direct_booking"  # never included in rental_cart
PAYMENT_DRAFT_KEY = "pending_payment"
PAYMENT_DRAFT_LIFETIME = 15 * 60  # expire unpaid checkout drafts after 15 minutes


def _payment_draft():
    """Read a short-lived, signed-session checkout draft; it is not an order."""
    draft = session.get(PAYMENT_DRAFT_KEY)
    if not isinstance(draft, dict):
        return None
    try:
        valid = (
            draft.get("user_id") == session.get("user_id")
            and draft.get("payment_method") in svc.PAYMENT_METHODS
            and draft.get("receiving_method") in svc.RECEIVING_METHODS
            and bool(draft.get("items"))
            and 0 <= time.time() - float(draft.get("created_at", 0)) < PAYMENT_DRAFT_LIFETIME
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        session.pop(PAYMENT_DRAFT_KEY, None)
        return None
    if not draft.get("transfer_reference"):
        draft = dict(draft)
        draft["transfer_reference"] = "G12" + secrets.token_hex(6).upper()
        session[PAYMENT_DRAFT_KEY] = draft
        session.modified = True
    return draft



def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify(ok=False, message="Vui lòng đăng nhập."), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


def _get_cart():
    return session.get(CART_KEY, [])


def _save_cart(cart):
    session[CART_KEY] = cart
    session.modified = True


def _get_direct_booking():
    return session.get(DIRECT_BOOKING_KEY)


def _save_direct_booking(item):
    session[DIRECT_BOOKING_KEY] = item
    session.modified = True


def _summary_json(summary):
    return {
        "ok": True,
        "is_valid": summary["is_valid"],
        "selected_count": summary["selected_count"],
        "total_count": summary["total_count"],
        "all_selected": summary["all_selected"],
        "subtotal": int(summary["subtotal"]),
        "delivery_fee": int(summary["delivery_fee"]),
        "total": int(summary["total"]),
        "deposit": int(summary["deposit"]),
        "count": len(summary["items"]),
        "receiving_method": summary.get("receiving_method", "PICKUP"),
        "items": [
            {
                "car_id": i["car_id"],
                "selected": i["selected"],
                "pickup_date": i["pickup_date"],
                "return_date": i["return_date"],
                "pickup_location": i["pickup_location"],
                "return_location": i["return_location"],
                "rental_days": i["rental_days"],
                "line_total": int(i["line_total"]),
                "error": i["error"],
                "overlap_conflict": i["overlap_conflict"],
            }
            for i in summary["items"]
        ],
    }


@booking_bp.app_template_filter("vnd")
def vnd(value):
    try:
        return f"{int(round(float(value))):,}".replace(",", ".") + "₫"
    except (TypeError, ValueError):
        return "0₫"


@booking_bp.app_template_filter("vn_date")
def vn_date(value):
    d = svc.parse_date(value)
    if d is None:
        return "--/--/----"
    return d.strftime("%d/%m/%Y")


@booking_bp.app_template_filter("en_date")
def en_date(value):
    d = svc.parse_date(value)
    if d is None:
        return "Select date"
    return d.strftime("%b %d, %Y")


@booking_bp.app_template_filter("dt_str")
def dt_str(value):
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value or "")


@booking_bp.app_template_filter("car_img_url")
def car_img_url(pictures):
    """Resolve Cars.pictures to a valid image URL.

    Supports:
      - Bare filenames from Database/sample_data_vehicles.sql
        (e.g. 'toyotavios2023.webp' -> '/static/images/cars/toyotavios2023.webp')
      - Comma/semicolon/newline-separated image lists (takes the first image)
      - Absolute URLs ('http://...', 'https://...') or root-relative paths ('/static/...')
      - Fallback placeholder when empty
    """
    raw = (pictures or "").strip()
    if raw:
        first = raw.replace("\n", ",").replace(";", ",").split(",")[0].strip()
        if first:
            # Map legacy Booking image paths to current vehicle photos.
            legacy_booking_photos = {
                "car_vios.svg": "images/cars/toyotavios2023.webp",
                "car_city.svg": "images/cars/hondacity2022.webp",
                "car_vf3.svg": "images/cars/vinfast_vf3.jpg",
                "car_carnival.svg": "images/cars/kia_carnival.jpg",
            }
            picture_name = first.rsplit("/", 1)[-1].lower()
            is_booking_illustration = (
                "images/booking/" in first.lower()
                or first.lower().startswith("car_")
            )
            if is_booking_illustration:
                if picture_name in legacy_booking_photos:
                    return url_for("static", filename=legacy_booking_photos[picture_name])
                if picture_name == "car_vf5.svg":
                    # VinFast VF5 image: Wikimedia Commons CC0, photographer Bún bòa.
                    return "https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960"
            if first.startswith(("http://", "https://", "//", "/")):
                return first
            if first.startswith("static/"):
                return "/" + first
            if first.startswith("images/"):
                return url_for("static", filename=first)
            return url_for("static", filename="images/cars/" + first)
    return url_for("static", filename="images/cars/car-placeholder.svg")


@booking_bp.app_context_processor
def inject_booking_nav():
    cart = _get_cart()
    return {
        "nav_cart_count": len(cart),
        "nav_user_name": session.get("full_name") or "Group 12",
        "nav_logged_in": "user_id" in session,
    }


@booking_bp.route("/cart")
@login_required
def cart():
    keyword = request.args.get("q", "").strip()
    summary = svc.build_cart_summary(_get_cart())
    in_cart = {int(i["car_id"]) for i in _get_cart()}
    available_cars = [
        c for c in svc.get_available_cars(keyword=keyword) if c["carID"] not in in_cart
    ]
    return render_template(
        "booking/cart.html",
        summary=summary,
        cars=available_cars,
        search_query=keyword,
        locations=svc.LOCATIONS,
    )


@booking_bp.route("/cart/add/<int:car_id>", methods=["POST"])
@login_required
def cart_add(car_id):
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload or {}
    pickup = str(payload.get("pickup_date", "")).strip()
    return_ = str(payload.get("return_date", "")).strip()
    if not pickup or not return_:
        pickup, return_ = svc.default_rental_dates()

    pickup_loc = payload.get("pickup_location", svc.DEFAULT_LOCATION)
    return_loc = payload.get("return_location", svc.DEFAULT_LOCATION)

    cart_items, added, msg = svc.add_to_cart(
        _get_cart(),
        car_id,
        pickup_date=pickup,
        return_date=return_,
        selected=True,
        pickup_location=pickup_loc,
        return_location=return_loc,
    )
    _save_cart(cart_items)

    if request.is_json:
        return jsonify({**_summary_json(svc.build_cart_summary(cart_items)), "message": msg, "added": added})

    flash(msg, "success" if added else "error")
    return redirect(request.form.get("next") or url_for("booking.cart"))


@booking_bp.route("/book-now/<int:car_id>", methods=["POST"])
@login_required
def book_now(car_id):
    """Book one vehicle without reading or modifying any saved cart entry."""
    pickup = request.form.get("pickup_date", "").strip()
    return_ = request.form.get("return_date", "").strip()
    if not pickup or not return_:
        pickup, return_ = svc.default_rental_dates()

    item = {
        "car_id": car_id,
        "pickup_date": pickup,
        "return_date": return_,
        "selected": True,
        "pickup_location": svc.DEFAULT_LOCATION,
        "return_location": svc.DEFAULT_LOCATION,
    }
    summary = svc.build_cart_summary([item], selected_only=True)
    if not summary["is_valid"]:
        flash(next((i["error"] for i in summary["items"] if i["error"]),
                   "Không thể thuê ngay xe này."), "error")
        return redirect(url_for("cars"))
    _save_direct_booking(item)
    return redirect(url_for("booking.checkout", mode="now"))


@booking_bp.route("/cart/remove/<int:car_id>", methods=["POST"])
@login_required
def cart_remove(car_id):
    cart_items, removed = svc.remove_from_cart(_get_cart(), car_id)
    _save_cart(cart_items)
    if request.is_json:
        return jsonify(_summary_json(svc.build_cart_summary(cart_items)))
    flash(
        "Đã xóa xe khỏi giỏ hàng." if removed else "Xe không có trong giỏ hàng.",
        "success" if removed else "error",
    )
    return redirect(url_for("booking.cart"))


@booking_bp.route("/cart/remove-selected", methods=["POST"])
@login_required
def cart_remove_selected():
    cart_items, removed_count = svc.remove_selected_from_cart(_get_cart())
    _save_cart(cart_items)
    if request.is_json:
        return jsonify(
            {
                **_summary_json(svc.build_cart_summary(cart_items)),
                "removed_count": removed_count,
            }
        )
    if removed_count > 0:
        flash(f"Đã xóa {removed_count} xe đã chọn khỏi giỏ hàng.", "success")
    else:
        flash("Chưa có xe nào được chọn để xóa.", "error")
    return redirect(url_for("booking.cart"))


@booking_bp.route("/api/cart/dates", methods=["POST"])
@login_required
def api_cart_dates():
    """Update pickup/return dates of one car (or all selected cars on checkout)
    and return recalculated fees + overlap check results."""
    data = request.get_json(silent=True) or {}
    receiving = data.get("receiving_method", "PICKUP")
    if receiving not in svc.RECEIVING_METHODS:
        receiving = "PICKUP"

    if data.get("apply_selected"):
        pickup_location = (svc.SHOWROOM_LOCATION if receiving == "PICKUP"
                           else (data.get("pickup_location") or "").strip())
        return_location = data.get("return_location")
        if receiving == "PICKUP" and (
            not return_location or return_location == data.get("pickup_location")
        ):
            return_location = svc.SHOWROOM_LOCATION
        cart_items = svc.update_all_selected_dates(
            _get_cart(),
            data.get("pickup_date"),
            data.get("return_date"),
            pickup_location or None,
            return_location,
        )
        _save_cart(cart_items)
        return jsonify(
            _summary_json(
                svc.build_cart_summary(
                    cart_items, receiving_method=receiving, selected_only=True
                )
            )
        )

    try:
        car_id = int(data.get("car_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="Xe không hợp lệ."), 400

    cart_items = svc.update_cart_dates(
        _get_cart(), car_id, data.get("pickup_date"), data.get("return_date")
    )
    if data.get("pickup_location") or data.get("return_location"):
        cart_items = svc.update_cart_locations(
            cart_items,
            car_id,
            data.get("pickup_location"),
            data.get("return_location"),
        )
    _save_cart(cart_items)
    return jsonify(_summary_json(svc.build_cart_summary(cart_items, receiving_method=receiving)))


@booking_bp.route("/api/book-now/dates", methods=["POST"])
@login_required
def api_direct_booking_dates():
    """Update instant checkout dates without changing rental_cart."""
    item = _get_direct_booking()
    if not item:
        return jsonify(ok=False, message="Không có xe đang thuê ngay."), 400
    data = request.get_json(silent=True) or {}
    receiving = data.get("receiving_method", "PICKUP")
    if receiving not in svc.RECEIVING_METHODS:
        receiving = "PICKUP"
    pickup_location = (svc.SHOWROOM_LOCATION if receiving == "PICKUP"
                       else (data.get("pickup_location") or "").strip())
    return_location = data.get("return_location")
    if receiving == "PICKUP" and (
        not return_location or return_location == data.get("pickup_location")
    ):
        return_location = svc.SHOWROOM_LOCATION
    items = svc.update_all_selected_dates(
        [item], data.get("pickup_date"), data.get("return_date"),
        pickup_location or None, return_location,
    )
    _save_direct_booking(items[0])
    return jsonify(_summary_json(svc.build_cart_summary(
        items, receiving_method=receiving, selected_only=True
    )))


@booking_bp.route("/api/book-now/summary", methods=["POST"])
@login_required
def api_direct_booking_summary():
    item = _get_direct_booking()
    if not item:
        return jsonify(ok=False, message="Không có xe đang thuê ngay."), 400
    data = request.get_json(silent=True) or {}
    receiving = data.get("receiving_method", "PICKUP")
    if receiving not in svc.RECEIVING_METHODS:
        receiving = "PICKUP"
    return jsonify(_summary_json(svc.build_cart_summary(
        [item], receiving_method=receiving, selected_only=True
    )))


@booking_bp.route("/api/cart/select", methods=["POST"])
@login_required
def api_cart_select():
    """Toggle checkbox selection for one car or all cars."""
    data = request.get_json(silent=True) or {}
    if "select_all" in data:
        cart_items = svc.set_all_selected(_get_cart(), bool(data["select_all"]))
    else:
        try:
            car_id = int(data.get("car_id"))
        except (TypeError, ValueError):
            return jsonify(ok=False, message="Xe không hợp lệ."), 400
        cart_items = svc.set_item_selected(_get_cart(), car_id, bool(data.get("selected", True)))
    _save_cart(cart_items)
    return jsonify(_summary_json(svc.build_cart_summary(cart_items)))


@booking_bp.route("/api/cart/summary", methods=["GET", "POST"])
@login_required
def api_cart_summary():
    data = request.get_json(silent=True) or {}
    receiving = data.get("receiving_method") or request.args.get("receiving_method", "PICKUP")
    if receiving not in svc.RECEIVING_METHODS:
        receiving = "PICKUP"
    selected_only = bool(data.get("selected_only") or request.args.get("selected_only"))
    return jsonify(
        _summary_json(
            svc.build_cart_summary(
                _get_cart(), receiving_method=receiving, selected_only=selected_only
            )
        )
    )


@booking_bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    direct_mode = request.values.get("mode") == "now"
    if direct_mode:
        item = _get_direct_booking()
        if not item:
            flash("Vui lòng chọn một xe để thuê ngay.", "error")
            return redirect(url_for("cars"))
        checkout_items = [item]
    else:
        checkout_items = _get_cart()

    selected_items = svc.get_selected_cart_items(checkout_items)
    if not selected_items:
        flash("Vui lòng chọn ít nhất một xe để đặt.", "error")
        return redirect(url_for("cars") if direct_mode else url_for("booking.cart"))

    receiving = request.values.get("receiving_method", "PICKUP")
    if receiving not in svc.RECEIVING_METHODS:
        receiving = "PICKUP"
    checkout_again = url_for(
        "booking.checkout", receiving_method=receiving,
        **({"mode": "now"} if direct_mode else {})
    )

    if request.method == "POST":
        form_pickup = request.form.get("pickup_date", "").strip()
        form_return = request.form.get("return_date", "").strip()
        form_pickup_loc = request.form.get("pickup_location", "").strip()
        form_return_loc = request.form.get("return_location", "").strip()
        return_choice = request.form.get("return_choice")

        # Validate pickup addresses server-side to reject forged locations.
        if receiving == "PICKUP":
            form_pickup_loc = svc.SHOWROOM_LOCATION
        elif not form_pickup_loc or form_pickup_loc in svc.LOCATIONS:
            flash("Vui lòng nhập địa chỉ giao xe tận nơi.", "error")
            return redirect(checkout_again)
        if len(form_pickup_loc) > 255:
            flash("Địa chỉ điểm đón quá dài (tối đa 255 ký tự).", "error")
            return redirect(checkout_again)

        if return_choice is not None:
            if return_choice not in ("SAME_AS_PICKUP", "SHOWROOM"):
                flash("Vui lòng chọn địa điểm trả xe hợp lệ.", "error")
                return redirect(checkout_again)
            form_return_loc = (
                svc.SHOWROOM_LOCATION if return_choice == "SHOWROOM"
                else form_pickup_loc
            )
        elif receiving == "PICKUP":
            form_return_loc = svc.SHOWROOM_LOCATION

        dates_modified = request.form.get("dates_modified") == "1"
        if form_pickup and form_return and (len(selected_items) == 1 or dates_modified):
            checkout_items = svc.update_all_selected_dates(
                checkout_items, form_pickup, form_return,
                form_pickup_loc or None, form_return_loc or None,
            )
            if direct_mode:
                _save_direct_booking(checkout_items[0])
            else:
                _save_cart(checkout_items)
            selected_items = svc.get_selected_cart_items(checkout_items)
        elif form_pickup_loc or form_return_loc:
            checkout_items = svc.update_all_selected_dates(
                checkout_items, None, None,
                form_pickup_loc or None, form_return_loc or None,
            )
            if direct_mode:
                _save_direct_booking(checkout_items[0])
            else:
                _save_cart(checkout_items)
            selected_items = svc.get_selected_cart_items(checkout_items)

        if request.form.get("agree_terms") != "on":
            flash("Vui lòng đồng ý với Điều khoản và Chính sách bảo mật trước khi đặt xe.", "error")
            return redirect(checkout_again)

        payment_method = request.form.get("payment_method", "E_WALLET")
        if payment_method not in svc.PAYMENT_METHODS:
            flash("Please select a valid payment method.", "error")
            return redirect(checkout_again)
        summary = svc.build_cart_summary(
            selected_items, receiving_method=receiving, selected_only=True
        )
        if not summary["is_valid"]:
            flash(next((i["error"] for i in summary["items"] if i["error"]),
                       "Please check your rental dates."), "error")
            return redirect(checkout_again)

        session[PAYMENT_DRAFT_KEY] = {
            "user_id": session["user_id"],
            "items": selected_items,
            "receiving_method": receiving,
            "payment_method": payment_method,
            "direct_mode": direct_mode,
            "created_at": int(time.time()),
            "csrf": secrets.token_urlsafe(32),
            "transfer_reference": "G12" + secrets.token_hex(6).upper(),
        }
        session.modified = True
        return redirect(url_for("booking.payment_page"))

    summary = svc.build_cart_summary(
        checkout_items, receiving_method=receiving, selected_only=True
    )
    if not summary["is_valid"]:
        first_err = next((i["error"] for i in summary["items"] if i["error"]), "")
        flash(
            first_err or "Vui lòng kiểm tra lại ngày nhận/trả xe.",
            "error",
        )
        return redirect(url_for("cars") if direct_mode else url_for("booking.cart"))

    renter = svc.get_renter_profile(session["user_id"])
    first_item = summary["items"][0]
    return render_template(
        "booking/checkout.html",
        summary=summary,
        direct_mode=direct_mode,
        receiving=receiving,
        first_item=first_item,
        locations=svc.LOCATIONS,
        showroom_location=svc.SHOWROOM_LOCATION,
        renter=renter,
        full_name=session.get("full_name", ""),
        free_delivery_threshold=int(svc.FREE_DELIVERY_THRESHOLD),
    )


def _demo_payment_enabled():
    """Local development only; never enable simulated receipts on public servers."""
    flag = os.getenv("DEMO_PAYMENT_MODE", "1" if current_app.debug else "0")
    return (
        (current_app.debug or current_app.testing)
        and str(flag).strip().lower() in ("1", "true", "yes", "on")
        and request.remote_addr in ("127.0.0.1", "::1")
    )


@booking_bp.route("/payment", methods=["GET", "POST"])
@login_required
def payment_page():
    draft = _payment_draft()
    if not draft:
        flash("No pending checkout or the payment session expired. Please review your booking.", "error")
        return redirect(url_for("booking.cart"))

    summary = svc.build_cart_summary(
        draft["items"], receiving_method=draft["receiving_method"], selected_only=True
    )
    if not summary["is_valid"]:
        session.pop(PAYMENT_DRAFT_KEY, None)
        flash(next((i["error"] for i in summary["items"] if i["error"]),
                   "The selected car is no longer available."), "error")
        return redirect(url_for(
            "booking.checkout", **({"mode": "now"} if draft["direct_mode"] else {})
        ))

    payment_error = None
    demo_mode = _demo_payment_enabled()
    if request.method == "POST":
        token = str(request.form.get("payment_csrf") or "")
        expected = str(draft.get("csrf") or "")
        if not expected or not secrets.compare_digest(token, expected):
            return "Invalid payment request.", 400

        action = request.form.get("payment_action")
        if action == "declined":
            payment_error = "Demo payment declined. No order was placed. Please try again."
        elif action != "confirm":
            return "Invalid payment action.", 400
        else:
            try:
                outcome = "success" if draft["payment_method"] == "E_WALLET" else "confirmed"
                order_id = svc.place_order(
                    user_id=session["user_id"],
                    cart=draft["items"],
                    receiving_method=draft["receiving_method"],
                    payment_method=draft["payment_method"],
                    demo_outcome=outcome,
                    transfer_reference=draft.get("transfer_reference"),
                )
            except svc.BookingError as exc:
                payment_error = str(exc)
            else:
                if draft["direct_mode"]:
                    if session.get(DIRECT_BOOKING_KEY) == draft["items"][0]:
                        session.pop(DIRECT_BOOKING_KEY, None)
                else:
                    def was_purchased(item):
                        return any(
                            item["car_id"] == staged["car_id"]
                            and item["pickup_date"] == staged["pickup_date"]
                            and item["return_date"] == staged["return_date"]
                            for staged in draft["items"]
                        )
                    _save_cart([item for item in _get_cart() if not was_purchased(item)])
                session.pop(PAYMENT_DRAFT_KEY, None)
                flash(f"Demo payment confirmed. Booking #{order_id} was created.", "success")
                return redirect(url_for("booking.payment_receipt", order_id=order_id))

    # QR display does not prove payment receipt.
    qr_image = None
    qr_kind = None
    bank_details = None
    if not demo_mode and draft["payment_method"] == "BANK_TRANSFER":
        qr_image = payment_qr.bank_transfer_qr(
            summary["deposit"], draft["transfer_reference"]
        )
        if qr_image:
            qr_kind = "BANK_TRANSFER"
            bank_details = {
                "bank": os.getenv("PAYMENT_BANK_BIN", "").strip(),
                "account": os.getenv("PAYMENT_BANK_ACCOUNT", "").strip(),
                "holder": os.getenv("PAYMENT_BANK_HOLDER", "").strip(),
            }
    elif not demo_mode and draft["payment_method"] == "E_WALLET":
        qr_file = payment_qr.momo_merchant_qr_filename()
        if qr_file:
            relative_file = os.path.join("images", "payments", qr_file)
            absolute_file = os.path.join(
                current_app.static_folder, relative_file
            )
            if os.path.isfile(absolute_file):
                qr_image = url_for(
                    "static", filename="images/payments/" + qr_file
                )
                qr_kind = "MOMO_STATIC"

    method_labels = svc.PAYMENT_METHOD_LABELS
    return render_template(
        "booking/payment.html",
        draft=draft,
        summary=summary,
        payment_method_label=method_labels[draft["payment_method"]],
        payment_error=payment_error,
        qr_image=qr_image,
        qr_kind=qr_kind,
        bank_details=bank_details,
        demo_mode=demo_mode,
        direct_mode=draft["direct_mode"],
    )


def _collection_csrf(key):
    if key not in session:
        session[key] = secrets.token_urlsafe(32)
    return session[key]


def _require_collection_csrf(key):
    expected = str(session.get(key) or "")
    provided = str(request.form.get("csrf_token") or "")
    if not expected or not secrets.compare_digest(expected, provided):
        abort(400)


def _momo_image_for_payment():
    name = payment_qr.momo_merchant_qr_filename()
    if not name:
        return None
    path = os.path.join(current_app.static_folder, "images", "payments", name)
    return (url_for("static", filename="images/payments/" + name)
            if os.path.isfile(path) else None)


@booking_bp.route("/orders/<int:order_id>/pay-remaining", methods=["GET", "POST"])
@login_required
def pay_remaining(order_id):
    """Customer requests collection of the unpaid amount; never self-approves."""
    if request.method == "POST":
        _require_collection_csrf("collection_csrf")
        action = request.form.get("action")
        try:
            if action == "request":
                method = request.form.get("payment_method", "")
                collection_service.request_remaining_payment(
                    session["user_id"], order_id, method
                )
                flash("Payment request submitted. Awaiting staff verification.", "success")
            elif action == "cancel_pending":
                collection_service.cancel_remaining_request(session["user_id"], order_id)
                flash("Pending request cancelled. You may choose another method.", "success")
            elif action in ("demo_success", "demo_failed"):
                if not _demo_payment_enabled():
                    abort(404)
                order = svc.get_order_payment_details(session["user_id"], order_id)
                payment = order.get("pending_balance_request")
                if not payment:
                    raise collection_service.CollectionError("No remaining payment is awaiting a demo result.")
                outcome = "success" if action == "demo_success" else "failed"
                collection_service.simulate_collection(
                    session["user_id"], order_id, payment["paymentID"], outcome
                )
                if outcome == "success":
                    flash("DEMO ONLY: Remaining balance marked paid. No money moved.", "success")
                    return redirect(url_for("booking.payment_receipt", order_id=order_id))
                flash("Demo payment failed. You can choose a method and retry.", "error")
            else:
                abort(400)
        except collection_service.CollectionError as exc:
            flash(str(exc), "error")
        return redirect(url_for("booking.pay_remaining", order_id=order_id))

    try:
        order = svc.get_order_payment_details(session["user_id"], order_id)
    except svc.BookingError:
        abort(404)

    payment = order.get("pending_balance_request")
    qr_image = None
    qr_type = None
    bank_details = None
    if payment:
        if payment["paymentMethod"] == "BANK_TRANSFER":
            qr_image = payment_qr.bank_transfer_qr(
                payment["amount"], payment["transactionCode"]
            )
            if qr_image:
                qr_type = "BANK_TRANSFER"
                bank_details = {
                    "bank": os.getenv("PAYMENT_BANK_BIN", "").strip(),
                    "account": os.getenv("PAYMENT_BANK_ACCOUNT", "").strip(),
                    "holder": os.getenv("PAYMENT_BANK_HOLDER", "").strip(),
                }
        elif payment["paymentMethod"] == "E_WALLET":
            qr_image = _momo_image_for_payment()
            if qr_image:
                qr_type = "MOMO_STATIC"

    return render_template(
        "booking/pay_remaining.html",
        order=order,
        payment=payment,
        qr_image=qr_image,
        qr_type=qr_type,
        bank_details=bank_details,
        payment_methods=collection_service.SUPPORTED_BALANCE_METHODS,
        demo_mode=_demo_payment_enabled(),
        csrf_token=_collection_csrf("collection_csrf"),
    )


def admin_payment_required(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if str(session.get("role") or "").upper() != "ADMIN":
            abort(403)
        if not collection_service.is_active_admin(session["user_id"]):
            abort(403)
        return view(*args, **kwargs)
    return guarded


@booking_bp.route("/admin/payments")
@admin_payment_required
def admin_payments():
    pending = collection_service.list_pending_collections()
    return render_template(
        "booking/admin_payments.html", pending=pending,
        csrf_token=_collection_csrf("admin_payment_csrf")
    )


@booking_bp.route("/admin/payments/<int:payment_id>/confirm", methods=["POST"])
@admin_payment_required
def admin_confirm_payment(payment_id):
    _require_collection_csrf("admin_payment_csrf")
    if request.form.get("verified") != "yes":
        flash("Verify the actual deposit in the bank / wallet / cash ledger first.", "error")
        return redirect(url_for("booking.admin_payments"))
    try:
        order_id = collection_service.confirm_collection(payment_id)
        flash(f"Payment #{payment_id} verified for booking #{order_id}.", "success")
    except collection_service.CollectionError as exc:
        flash(str(exc), "error")
    return redirect(url_for("booking.admin_payments"))


@booking_bp.route("/orders")
@login_required
def my_orders():
    orders = svc.get_user_orders(session["user_id"])
    return render_template("booking/orders.html", orders=orders)


@booking_bp.route("/orders/<int:order_id>/payment")
@login_required
def payment_receipt(order_id):
    try:
        order = svc.get_order_payment_details(session["user_id"], order_id)
    except svc.BookingError:
        return render_template("error.html", error_code="404", error_message="Order not found."), 404
    return render_template(
        "booking/payment_receipt.html", order=order,
        demo_mode=_demo_payment_enabled(),
        demo_csrf=_collection_csrf("demo_payment_csrf"),
    )


@booking_bp.route("/orders/<int:order_id>/payment/demo", methods=["POST"])
@login_required
def demo_receive_initial_payment(order_id):
    if not _demo_payment_enabled():
        abort(404)
    _require_collection_csrf("demo_payment_csrf")
    if request.form.get("action") != "success":
        abort(400)
    try:
        order = svc.get_order_payment_details(session["user_id"], order_id)
    except svc.BookingError:
        abort(404)
    payment = next(
        (p for p in order["payments"]
         if p["paymentStatus"] == "Pending"
         and not str(p.get("transactionCode") or "").startswith("BAL-")), None
    )
    if not payment:
        flash("There is no pending initial payment to simulate.", "error")
        return redirect(url_for("booking.payment_receipt", order_id=order_id))
    try:
        collection_service.simulate_collection(
            session["user_id"], order_id, payment["paymentID"], "success"
        )
        flash("DEMO ONLY: Payment marked received. No real money moved.", "success")
    except collection_service.CollectionError as exc:
        flash(str(exc), "error")
    return redirect(url_for("booking.payment_receipt", order_id=order_id))


@booking_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    try:
        svc.cancel_order(session["user_id"], order_id)
        flash(f"Đã hủy đơn hàng #{order_id} thành công. Lịch xe đã được giải phóng.", "success")
    except svc.BookingError as exc:
        flash(str(exc), "error")
    return redirect(url_for("booking.my_orders"))
