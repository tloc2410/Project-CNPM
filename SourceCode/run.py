import os

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
from data.user_repository import find_user_by_email

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
    """Resolve the first stored picture to a usable URL."""
    name = vehicle_service.primary_picture_name(car)
    if not name:
        return url_for("static", filename="images/cars/car-placeholder.svg")
    if name.startswith(("http://", "https://", "//", "/")):
        return name
    return url_for("static", filename="images/cars/" + name)


def format_price(value):
    try:
        return f"{float(value):,.0f} ₫"
    except (TypeError, ValueError):
        return "—"


@app.context_processor
def inject_vehicle_helpers():
    return {
        "is_admin": lambda: vehicle_service.can_manage_vehicles(session),
        "car_image": car_image,
        "format_price": format_price,
        "status_label": vehicle_service.status_label,
    }


def _require_admin():
    """Backend permission check; never rely on the session role alone."""
    if not vehicle_service.can_manage_vehicles(session):
        abort(403)


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


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ---------------------------------------------------------------------------
# Customer vehicle pages
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    db_error = None
    featured = []
    types = []
    try:
        cars, _, _, _ = vehicle_service.list_vehicles({"sort": "popular"})
        featured = cars[:6]
        types = vehicle_service.list_car_types()
    except Exception as exc:
        app.logger.exception("Home vehicle query failed")
        db_error = str(exc)

    return render_template(
        "home.html", featured=featured, types=types, db_error=db_error
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

    return render_template("car_detail.html", car=car, related=related)


# ---------------------------------------------------------------------------
# Admin vehicle management
# ---------------------------------------------------------------------------
@app.route("/admin/cars")
def admin_cars():
    _require_admin()
    results, total, total_pages, filters = vehicle_service.list_vehicles(
        request.args
    )
    return render_template(
        "admin/cars.html",
        cars=results,
        total=total,
        total_pages=total_pages,
        filters=filters,
        types=_car_types_or_empty(),
        sorts=vehicle_service.SORT_OPTIONS,
        statuses=vehicle_service.CAR_STATUSES,
    )


@app.route("/admin/cars/new", methods=["GET", "POST"])
def admin_car_new():
    _require_admin()
    form = {"status": "available"}
    errors = {}

    if request.method == "POST":
        success, message, errors = vehicle_service.create_vehicle(request.form)
        flash(message, "success" if success else "error")
        if success:
            return redirect(url_for("admin_cars"))
        form = request.form

    return render_template(
        "admin/car_form.html",
        heading="Thêm xe mới",
        form=form,
        errors=errors,
        car=None,
        form_action=url_for("admin_car_new"),
        types=_car_types_or_empty(),
        statuses=vehicle_service.CAR_STATUSES,
    )


@app.route("/admin/cars/<int:car_id>/edit", methods=["GET", "POST"])
def admin_car_edit(car_id):
    _require_admin()
    car = vehicle_service.get_vehicle(car_id)
    if not car:
        abort(404)

    errors = {}
    if request.method == "POST":
        success, message, errors = vehicle_service.update_vehicle(
            car_id, request.form
        )
        flash(message, "success" if success else "error")
        form = request.form
        if success:
            return redirect(url_for("admin_cars"))
    else:
        form = {
            "code": car["code"],
            "name": car["name"],
            "type_id": car["TypeID"],
            "seats": car["numberOfSeats"],
            "price": car["pricePerDay"],
            "status": car["status"],
            "pictures": car["pictures"] or "",
            "description": car["description"] or "",
        }

    return render_template(
        "admin/car_form.html",
        heading=f"Sửa xe {car['code']}",
        form=form,
        errors=errors,
        car=car,
        form_action=url_for("admin_car_edit", car_id=car_id),
        types=_car_types_or_empty(),
        statuses=vehicle_service.CAR_STATUSES,
    )


@app.route("/admin/cars/<int:car_id>/delete", methods=["POST"])
def admin_car_delete(car_id):
    _require_admin()
    success, message = vehicle_service.delete_vehicle(car_id)
    flash(message, "success" if success else "error")
    return redirect(url_for("admin_cars"))


@app.route("/admin/cars/<int:car_id>/status", methods=["POST"])
def admin_car_status(car_id):
    _require_admin()
    success, message = vehicle_service.set_vehicle_status(
        car_id, request.form.get("status")
    )
    flash(message, "success" if success else "error")
    return redirect(url_for("admin_cars"))


@app.route("/admin/car-types", methods=["GET", "POST"])
def admin_car_types():
    _require_admin()
    form = {}
    errors = {}

    if request.method == "POST":
        success, message, errors = vehicle_service.create_car_type(request.form)
        flash(message, "success" if success else "error")
        if success:
            return redirect(url_for("admin_car_types"))
        form = request.form

    types = []
    try:
        types = vehicle_service.list_car_types_with_counts()
    except Exception:
        app.logger.exception("Could not load car types")

    return render_template(
        "admin/car_types.html", types=types, form=form, errors=errors
    )


@app.route("/admin/car-types/<int:type_id>/edit", methods=["POST"])
def admin_car_type_edit(type_id):
    _require_admin()
    success, message, errors = vehicle_service.update_car_type(
        type_id, request.form
    )
    flash(message, "success" if success else "error")
    if errors:
        for value in errors.values():
            flash(value, "error")
    return redirect(url_for("admin_car_types"))


@app.route("/admin/car-types/<int:type_id>/delete", methods=["POST"])
def admin_car_type_delete(type_id):
    _require_admin()
    success, message = vehicle_service.delete_car_type(type_id)
    flash(message, "success" if success else "error")
    return redirect(url_for("admin_car_types"))


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


from presentation.booking_routes import booking_bp
app.register_blueprint(booking_bp)

if __name__ == "__main__":
    app.run(debug=True)
