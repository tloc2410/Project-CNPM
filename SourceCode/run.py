import os
from data.user_repository import find_user_by_email
from flask import Flask, render_template, request, redirect, url_for, session
from business.auth_service import register_user, login_user
from dotenv import load_dotenv
load_dotenv()
from business.password_reset_service import (
    create_token_for_email,
    verify_reset_token,
    reset_password_with_token,
)
from business.reset_email import send_reset_email
from business.payment_service import process_payment
from business.order_service import list_orders_for_admin, change_order_status
from data.order_repository import get_order_by_id

app = Flask(
    __name__,
    template_folder="presentation/templates",
    static_folder="presentation/static"
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-group12")


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

    return f"Welcome, {session['full_name']}! Login successful."


@app.route("/payment/<int:order_id>", methods=["GET", "POST"])
def payment_checkout(order_id):
    order = get_order_by_id(order_id)
    amount = order["totalPrice"] if order else 0

    if request.method == "POST":
        method = request.form.get("payment_method", "")
        sim_outcome = request.form.get("sim_outcome", "success")
        ok, msg = process_payment(order_id, amount, method, sim_outcome)
        if ok:
            return render_template(
                "payment.html", order_id=order_id, amount=amount, message=msg
            )
        return render_template(
            "payment.html", order_id=order_id, amount=amount, error=msg
        )

    return render_template("payment.html", order_id=order_id, amount=amount)


@app.route("/admin/orders", methods=["GET"])
def admin_orders():
    if "user_id" not in session:
        return redirect(url_for("login"))

    ok, err, orders = list_orders_for_admin(session.get("role"))
    if not ok:
        return render_template("admin_orders.html", orders=[], error=err), 403

    return render_template(
        "admin_orders.html",
        orders=orders,
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
def admin_update_order_status(order_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    new_status = request.form.get("status", "")
    ok, msg = change_order_status(session.get("role"), order_id, new_status)
    if ok:
        return redirect(url_for("admin_orders", message=msg))
    return redirect(url_for("admin_orders", error=msg))


if __name__ == "__main__":
    app.run(debug=True)