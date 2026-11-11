from flask import Flask, render_template

app = Flask(
    __name__,
    template_folder="presentation/templates",
    static_folder="presentation/static"
)

@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/signup")
def signup():
    return render_template("signup.html")


# Trang quên mật khẩu
@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")


if __name__ == "__main__":
    app.run(debug=True)