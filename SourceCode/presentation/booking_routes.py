"""Flask Blueprint for module Rental Cart & Booking (Do Thu Thao).

Integrates cleanly with the Account/Auth session created in SourceCode/run.py:
  - session["user_id"]
  - session["full_name"]
  - session["role"]
"""

from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from business import booking_service as svc

booking_bp = Blueprint("booking", __name__)

CART_KEY = "rental_cart"


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
            # Booking's original demo rows saved illustrations in the Cars
            # table. Map those specific paths to photographs even when users
            # have not rerun Database/booking_setup.sql on their local MySQL.
            # Keep this in the Booking filter: its cards do not call run.car_image.
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
                    # Commons CC0 photograph of an actual VinFast VF 5.
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


# ------------------------------------------------------------------ cart
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
    # JSON requests are handled without navigation; ordinary POST forms still work.
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
        cart_items = svc.update_all_selected_dates(
            _get_cart(),
            data.get("pickup_date"),
            data.get("return_date"),
            data.get("pickup_location"),
            data.get("return_location"),
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


# ------------------------------------------------------------------ checkout
@booking_bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart_items = _get_cart()
    selected_items = svc.get_selected_cart_items(cart_items)
    if not selected_items:
        flash("Vui lòng chọn ít nhất một xe trong giỏ hàng trước khi thanh toán.", "error")
        return redirect(url_for("booking.cart"))

    receiving = request.values.get("receiving_method", "PICKUP")
    if receiving not in svc.RECEIVING_METHODS:
        receiving = "PICKUP"

    if request.method == "POST":
        # Sync date/location changes from Checkout form when single-car or explicitly modified
        form_pickup = request.form.get("pickup_date", "").strip()
        form_return = request.form.get("return_date", "").strip()
        form_pickup_loc = request.form.get("pickup_location", "").strip()
        form_return_loc = request.form.get("return_location", "").strip()
        return_choice = request.form.get("return_choice")
        # The Checkout UI accepts a user-entered pickup address and only
        # two return destinations. Recompute on the server; never trust the
        # hidden return_location field submitted by the browser.
        if return_choice is not None:
            if not form_pickup_loc:
                flash("Vui lòng nhập địa chỉ điểm đón xe.", "error")
                return redirect(url_for("booking.checkout", receiving_method=receiving))
            if len(form_pickup_loc) > 255:
                flash("Địa chỉ điểm đón quá dài (tối đa 255 ký tự).", "error")
                return redirect(url_for("booking.checkout", receiving_method=receiving))
            if return_choice not in ("SAME_AS_PICKUP", "SHOWROOM"):
                flash("Vui lòng chọn địa điểm trả xe hợp lệ.", "error")
                return redirect(url_for("booking.checkout", receiving_method=receiving))
            form_return_loc = (svc.SHOWROOM_LOCATION if return_choice == "SHOWROOM"
                               else form_pickup_loc)
        dates_modified = request.form.get("dates_modified") == "1"

        if form_pickup and form_return and (len(selected_items) == 1 or dates_modified):
            cart_items = svc.update_all_selected_dates(
                cart_items,
                form_pickup,
                form_return,
                form_pickup_loc or None,
                form_return_loc or None,
            )
            _save_cart(cart_items)
            selected_items = svc.get_selected_cart_items(cart_items)
        elif form_pickup_loc or form_return_loc:
            cart_items = svc.update_all_selected_dates(
                cart_items,
                None,
                None,
                form_pickup_loc or None,
                form_return_loc or None,
            )
            _save_cart(cart_items)
            selected_items = svc.get_selected_cart_items(cart_items)

        if request.form.get("agree_terms") != "on":
            flash("Vui lòng đồng ý với Điều khoản và Chính sách bảo mật trước khi đặt xe.", "error")
            return redirect(url_for("booking.checkout", receiving_method=receiving))

        payment_method = request.form.get("payment_method", "CARD")
        try:
            order_id = svc.place_order(
                user_id=session["user_id"],
                cart=selected_items,
                receiving_method=receiving,
                payment_method=payment_method,
            )
        except svc.BookingError as exc:
            flash(str(exc), "error")
            return redirect(url_for("booking.checkout", receiving_method=receiving))

        # Remove only the ordered cars from the session cart.
        remaining = svc.remove_car_ids_from_cart(
            cart_items, [i["car_id"] for i in selected_items]
        )
        _save_cart(remaining)
        flash(f"Đặt xe thành công! Mã đơn hàng của bạn là #{order_id}.", "success")
        return redirect(url_for("booking.my_orders"))

    summary = svc.build_cart_summary(
        cart_items, receiving_method=receiving, selected_only=True
    )
    if not summary["is_valid"]:
        first_err = next((i["error"] for i in summary["items"] if i["error"]), "")
        flash(
            first_err or "Vui lòng kiểm tra lại ngày nhận/trả xe trong giỏ hàng.",
            "error",
        )
        return redirect(url_for("booking.cart"))

    renter = svc.get_renter_profile(session["user_id"])
    first_item = summary["items"][0]
    return render_template(
        "booking/checkout.html",
        summary=summary,
        receiving=receiving,
        first_item=first_item,
        locations=svc.LOCATIONS,
        showroom_location=svc.SHOWROOM_LOCATION,
        renter=renter,
        full_name=session.get("full_name", ""),
        free_delivery_threshold=int(svc.FREE_DELIVERY_THRESHOLD),
    )


# ------------------------------------------------------------------ orders
@booking_bp.route("/orders")
@login_required
def my_orders():
    orders = svc.get_user_orders(session["user_id"])
    return render_template("booking/orders.html", orders=orders)


@booking_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    try:
        svc.cancel_order(session["user_id"], order_id)
        flash(f"Đã hủy đơn hàng #{order_id} thành công. Lịch xe đã được giải phóng.", "success")
    except svc.BookingError as exc:
        flash(str(exc), "error")
    return redirect(url_for("booking.my_orders"))
