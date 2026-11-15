import os
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
app = Flask(
    __name__,
    template_folder="presentation/templates",
    static_folder="presentation/static"
)
app.secret_key = os.environ["SECRET_KEY"]

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
            full_name, email, password
        )

        if success:
            return redirect(url_for("login"))

        return render_template("signup.html", error=message)

    return render_template("signup.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        message = (
            "If this email is registered, a password reset link "
            "will be sent. Please check your inbox."
        )

        try:
            token = create_token_for_email(email)

            if token:
                reset_url = url_for(
                    "reset_password",
                    token=token,
                    _external=True
                )
                send_reset_email(email, reset_url)

        except Exception:
            app.logger.exception("Password reset email failed")

        return render_template(
            "forgot_password.html",
            message=message
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



if __name__ == "__main__":
    app.run(debug=True)
