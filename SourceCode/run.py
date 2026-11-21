import os
import re
import secrets

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from dotenv import load_dotenv

from business import vehicle_service
from business.auth_service import register_user, login_user
from business.password_reset_service import (
    create_token_for_email,
    verify_reset_token,
    reset_password_with_token,
)
from business.reset_email import send_reset_email
from data.user_repository import find_user_by_email, update_user_profile

load_dotenv()

app = Flask(
    __name__,
    template_folder="presentation/templates",
    static_folder="presentation/static",
)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
if app.secret_key == "dev-only-change-me":
    app.logger.warning("SECRET_KEY is not set; using a development-only fallback.")


# ---------------------------------------------------------------------------
# Shared presentation helpers
# ---------------------------------------------------------------------------
def car_image(car):
    """Resolve a vehicle photo, including legacy image paths from booking demo rows."""
    image = vehicle_service.primary_picture_name(car)
    fallback = url_for("static", filename="images/cars/car-placeholder.svg")
    # Booking demo cars have legacy drawing paths. Resolve to real photos
    # even before the user updates existing MySQL records.
    code = str((car or {}).get("code", "")).upper()
    real_booking_photos = {
        "BOOK-VIOS-01": "images/cars/toyotavios2023.webp",
        "BOOK-CITY-02": "images/cars/hondacity2022.webp",
    }
    if code in real_booking_photos:
        return url_for("static", filename=real_booking_photos[code])
    if code == "BOOK-VF5-03":
        # Real VinFast VF5 photo; Wikimedia Commons CC0, photographer Bún bòa.
        return "https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960"
    if image:
        image = str(image).strip()
        if image.startswith(("http://", "https://")):
            return image
        if image.startswith("/static/"):
            rel = image.removeprefix("/static/")
        elif image.startswith("static/"):
            rel = image.removeprefix("static/")
        elif image.startswith("images/"):
            rel = image
        else:
            rel = "images/cars/" + image
        # Old Booking rows may point to SVG assets that are not part of this branch.
        if os.path.isfile(os.path.join(app.static_folder, rel.replace("/", os.sep))):
            return url_for("static", filename=rel)

    name = str((car or {}).get("name", "")).lower()
    for keyword, filename in (
        ("toyota vios", "toyotavios2023.webp"),
        ("honda city", "hondacity2022.webp"),
        ("kia morning", "kiamorning2022.webp"),
        ("mercedes", "marcedesc200202022.webp"),
        ("bmw", "bmw320i2023.webp"),
        ("mazda", "mazdacx-52023.webp"),
        ("toyota corolla", "toyotacorollacross.webp"),
        ("hyundai", "hyundaii102023.webp"),
        ("vinfast", "vinfastVFe34.webp"),
    ):
        if keyword in name:
            return url_for("static", filename="images/cars/" + filename)
    return fallback


def car_gallery(car):
    """Expose every stored car image without inventing missing photo angles."""
    import re
    raw = str((car or {}).get("pictures") or "")
    photos = []
    for name in re.split(r"[\n,;]+", raw):
        if name.strip():
            photo = car_image({**car, "pictures": name.strip()})
            if photo not in photos:
                photos.append(photo)
    return photos or [car_image(car)]

def format_price(value):
    try:
        return f"{float(value):,.0f} ₫"
    except (TypeError, ValueError):
        return "—"


@app.context_processor
def inject_vehicle_helpers():
    return {
        "car_image": car_image,
        "booking_enabled": "booking.cart_add" in app.view_functions,
        "format_price": format_price,
        "status_label": vehicle_service.status_label,
    }


def _car_types_or_empty():
    try:
        return vehicle_service.list_car_types()
    except Exception:
        app.logger.exception("Could not load car types")
        return []


# ---------------------------------------------------------------------------
# Authentication (existing module)
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        success, message, user = login_user(email, password)

        if success:
            session.clear()
            session["user_id"] = user["UserID"]
            session["full_name"] = user["fullName"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        return render_template("login.html", error=message)

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            return render_template(
                "signup.html",
                error="Mật khẩu xác nhận không khớp."
            )

        if request.form.get("agree_terms") != "on":
            return render_template(
                "signup.html",
                error="Vui lòng đồng ý với điều khoản."
            )

        success, message = register_user(
            full_name, phone, email, password
        )

        if success:
            return redirect(url_for("login"))

        return render_template("signup.html", error=message)

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for("home"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        user = find_user_by_email(email)

        if not user:
            return render_template(
                "forgot_password.html",
                error="This email does not exist."
            )

        try:
            token = create_token_for_email(email)

            reset_url = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            send_reset_email(email, reset_url)

            message = (
                "If this email is registered, a password reset link "
                "will be sent. Please check your inbox."
            )

            return render_template(
                "forgot_password.html",
                message=message
            )

        except Exception:
            app.logger.exception("Password reset email failed")

            return render_template(
                "forgot_password.html",
                error="Unable to send reset email. Please try again."
            )

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if verify_reset_token(token) is None:
        return render_template(
            "reset_password.html",
            error="This reset link is invalid, expired, or already used."
        ), 400

    if request.method == "POST":
        success, message = reset_password_with_token(
            token,
            request.form.get("password", ""),
            request.form.get("confirm_password", "")
        )

        if success:
            return render_template(
                "reset_password.html",
                message=message
            )

        return render_template(
            "reset_password.html",
            error=message
        ), 400

    return render_template("reset_password.html")


# Customer account center: Shopee-style order tabs adapted to rentals.
_ACCOUNT_ORDER_GROUPS = {
    "PENDING": "pending", "NEW": "pending",
    "CONFIRMED": "confirmed",
    "RENTED": "renting", "ONGOING": "renting",
    "IN_PROGRESS": "renting", "IN_USE": "renting",
    "PICKED_UP": "renting", "ACTIVE": "renting",
    "COMPLETED": "completed", "RETURNED": "completed",
    "CANCELLED": "cancelled", "CANCELED": "cancelled",
}
_ACCOUNT_TABS = (
    ("all", "All Orders"),
    ("pending", "Pending"),
    ("confirmed", "Confirmed"),
    ("renting", "Renting"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
)


def _account_order_group(status):
    return _ACCOUNT_ORDER_GROUPS.get(str(status or "").upper(), "other")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    from business import booking_service

    section = request.args.get("section", "orders")
    if section not in ("orders", "profile"):
        section = "orders"
    status = request.args.get("status", "all")
    if status not in dict(_ACCOUNT_TABS):
        status = "all"
    query = request.args.get("q", "").strip()[:80]
    user = booking_service.get_renter_profile(session["user_id"])
    if not user:
        flash("Account information not found. Please sign in again.", "error")
        return redirect(url_for("logout"))

    if "account_profile_csrf" not in session:
        session["account_profile_csrf"] = secrets.token_urlsafe(24)

    orders = booking_service.get_user_orders(session["user_id"]) if section == "orders" else []
    counts = {"all": len(orders), **{
        tab: sum(_account_order_group(o.get("status")) == tab for o in orders)
        for tab, _ in _ACCOUNT_TABS if tab != "all"
    }}
    filtered = [
        o for o in orders
        if (status == "all" or _account_order_group(o.get("status")) == status)
        and (not query or query.casefold() in str(o.get("oderID", "")).casefold()
             or any(query.casefold() in str(i.get("carName", "")).casefold()
                    for i in o.get("items", [])))
    ]
    return render_template(
        "dashboard.html", section=section, profile=user, orders=filtered,
        order_counts=counts, order_tabs=_ACCOUNT_TABS, active_status=status,
        order_query=query, profile_csrf=session["account_profile_csrf"],
        order_status_group=_account_order_group,
    )


@app.route("/account/profile", methods=["POST"])
def account_update_profile():
    """A signed-in customer may edit only their own non-sensitive profile fields."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    csrf = request.form.get("csrf_token", "")
    expected = session.get("account_profile_csrf", "")
    if not expected or not secrets.compare_digest(csrf, expected):
        abort(400)

    full_name = request.form.get("full_name", "").strip()
    phone = re.sub(r"[\s().-]", "", request.form.get("phone", "").strip())
    if phone.startswith("+84"):
        phone = "0" + phone[3:]
    address = request.form.get("address", "").strip()
    if not (2 <= len(full_name) <= 100):
        flash("Your full name must be between 2 and 100 characters.", "error")
    elif not re.fullmatch(r"0[35789][0-9]{8}", phone):
        flash("Please enter a valid phone number.", "error")
    elif len(address) > 255:
        flash("Your address cannot exceed 255 characters.", "error")
    else:
        try:
            saved, message = update_user_profile(
                session["user_id"], full_name, phone, address
            )
            flash(message, "success" if saved else "error")
            if saved:
                session["full_name"] = full_name
        except Exception:
            app.logger.exception("Account profile update failed")
            flash("Unable to update your profile. Please try again.", "error")
    return redirect(url_for("dashboard", section="profile"))


# ---------------------------------------------------------------------------
# Customer vehicle pages
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    db_error = None
    featured = []
    types = []
    spotlight = []
    brand_cars = {brand: [] for brand in ("VinFast", "KIA", "Toyota", "BMW")}
    vehicle_showcase = []
    try:
        all_cars, _, total_pages, _ = vehicle_service.list_vehicles({"sort": "popular"})
        # Collect the remaining vehicle pages so a brand is not hidden
        # simply because it was absent from the top twelve cars.
        all_cars = list(all_cars)
        for page in range(2, min(total_pages, 10) + 1):
            next_cars, _, _, _ = vehicle_service.list_vehicles(
                {"sort": "popular", "page": page}
            )
            all_cars.extend(next_cars)
        featured = all_cars[:6]
        brands = ("VinFast", "KIA", "Toyota", "BMW")
        brand_cars = {brand: [] for brand in brands}
        for car in all_cars:
            name = str(car.get("name") or "").casefold()
            for brand in brands:
                if brand.casefold() in name and len(brand_cars[brand]) < 2:
                    brand_cars[brand].append(car)
        types = vehicle_service.list_car_types()
        def pick(match):
            return next((c for c in all_cars if match in c["name"].lower()), None)
        spotlight = [c for c in (pick("vinfast vf 5"), pick("vinfast vf 3")) if c]
        for car in all_cars:
            if len(spotlight) >= 2:
                break
            if car not in spotlight:
                spotlight.append(car)
        for fragment in ("toyota vios", "honda city", "vinfast vf 5",
                         "hyundai accent", "mazda 3", "kia morning"):
            selected = pick(fragment)
            if selected and selected not in vehicle_showcase:
                vehicle_showcase.append(selected)
        for car in all_cars:
            if len(vehicle_showcase) >= 6:
                break
            if car not in vehicle_showcase:
                vehicle_showcase.append(car)
    except Exception as exc:
        app.logger.exception("Home vehicle query failed")
        db_error = str(exc)

    return render_template(
        "home.html", featured=featured, spotlight=spotlight,
        brand_cars=brand_cars,
        vehicle_showcase=vehicle_showcase, types=types, db_error=db_error
    )


@app.route("/cars")
def cars():
    db_error = None
    try:
        results, total, total_pages, filters = vehicle_service.list_vehicles(
            request.args
        )
    except Exception as exc:
        app.logger.exception("Vehicle listing query failed")
        results, total, total_pages = [], 0, 1
        filters = vehicle_service.normalize_filters(request.args)
        db_error = str(exc)

    return render_template(
        "cars.html",
        cars=results,
        total=total,
        total_pages=total_pages,
        filters=filters,
        types=_car_types_or_empty(),
        sorts=vehicle_service.SORT_OPTIONS,
        statuses=vehicle_service.CAR_STATUSES,
        db_error=db_error,
    )


@app.route("/cars/<int:car_id>")
def car_detail(car_id):
    try:
        car = vehicle_service.get_vehicle(car_id, count_view=True)
    except Exception:
        app.logger.exception("Could not load car %s", car_id)
        flash("Không thể tải dữ liệu xe. Vui lòng thử lại.", "error")
        return redirect(url_for("cars"))

    if not car:
        abort(404)

    related = []
    try:
        rows, _, _, _ = vehicle_service.list_vehicles(
            {"type_id": car["TypeID"], "sort": "popular"}
        )
        related = [row for row in rows if row["carID"] != car_id][:3]
    except Exception:
        app.logger.exception("Could not load related cars")

    return render_template("car_detail.html", car=car, related=related, gallery=car_gallery(car))


# ---------------------------------------------------------------------------
# Admin vehicle management removed: assigned to a separate module.


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden(error):
    return render_template(
        "error.html", error_code="403", error_message="Bạn không có quyền truy cập trang này."
    ), 403


@app.errorhandler(404)
def not_found(error):
    return render_template(
        "error.html", error_code="404", error_message="Không tìm thấy trang hoặc xe yêu cầu."
    ), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template(
        "error.html", error_code="500", error_message="Đã xảy ra lỗi máy chủ. Vui lòng thử lại."
    ), 500


# Register Thu Thao's rental cart and booking routes in the shared Flask app.
# The customer Figma pages, authentication routes and MySQL connection stay intact.
from presentation.booking_routes import booking_bp
app.register_blueprint(booking_bp)


if __name__ == "__main__":
    app.run(debug=True)
