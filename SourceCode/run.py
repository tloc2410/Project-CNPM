import inspect
import os
from urllib.parse import quote
from flask import Flask, redirect, render_template, request, session, url_for

import business.vehicle_service as vehicle_service
import data.vehicle_repository as vehicle_repository  # noqa: F401


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "presentation", "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "group12-car-rental-secret-key")

ALLOWED_STATUSES = ["Available", "Rented", "Under maintenance"]


def _get_role() -> str:
    return (session.get("role") or "ADMIN").upper()


def _is_admin() -> bool:
    return _get_role() == "ADMIN"


def _redirect_vehicles(message: str = None, error: str = None):
    if message:
        return redirect(f"/admin/vehicles?message={quote(str(message))}")
    if error:
        return redirect(f"/admin/vehicles?error={quote(str(error))}")
    return redirect("/admin/vehicles")


def _invoke(func_name: str, role: str, payload: dict = None, extra_args: list = None):
    fn = getattr(vehicle_service, func_name, None)
    if fn is None:
        return False, f"Thiếu hàm '{func_name}' trong business/vehicle_service.py"

    extra_args = extra_args or []
    sig = inspect.signature(fn)
    params = [
        p for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]

    if payload is None:
        return fn(role, *extra_args)

    if len(params) == 2 and not extra_args:
        return fn(role, payload)

    ordered_keys = [
        "name",
        "license_plate",
        "seats",
        "type_id",
        "daily_price",
        "status",
    ]
    kw = {}
    for p in params[1:]:
        if p.name in payload:
            kw[p.name] = payload[p.name]
        elif p.name in ("vehicle_id", "id") and extra_args:
            kw[p.name] = extra_args[0]

    if kw and len(kw) == len(params) - 1:
        return fn(role, **kw)

    positional_vals = [payload.get(k) for k in ordered_keys if k in payload]
    if extra_args:
        return fn(role, extra_args[0], *positional_vals)
    return fn(role, *positional_vals)


def _load_fleet_data():
    role = _get_role()
    fn = getattr(vehicle_service, "list_admin_vehicle_data", None)
    if fn is None:
        return False, "Thiếu hàm 'list_admin_vehicle_data' trong business/vehicle_service.py", [], []

    result = fn(role)
    if isinstance(result, tuple):
        if len(result) == 4:
            ok, err, vehicles, vehicle_types = result
            return bool(ok), err, vehicles or [], vehicle_types or []
        if len(result) == 2:
            data, err = result
            if isinstance(data, dict):
                return True, err, data.get("vehicles") or [], data.get("vehicle_types") or []
    return False, "Dữ liệu trả về từ list_admin_vehicle_data không hợp lệ.", [], []


@app.route("/")
def index():
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    ok, err, vehicles, vehicle_types = _load_fleet_data()
    available_count = sum(1 for v in vehicles if v.get("status") == "Available")
    return render_template(
        "admin_dashboard.html",
        vehicles=vehicles,
        vehicle_types=vehicle_types,
        total_vehicles=len(vehicles),
        total_types=len(vehicle_types),
        available_vehicles=available_count,
        error=err if not ok else None,
    )


@app.route("/payment")
@app.route("/checkout")
def payment_page():
    return render_template("payment.html")


@app.route("/admin/vehicles", methods=["GET"])
def admin_vehicles():
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    ok, err, vehicles, vehicle_types = _load_fleet_data()
    message = request.args.get("message")
    error_msg = request.args.get("error") or (err if not ok else None)

    return render_template(
        "admin_vehicles.html",
        vehicles=vehicles,
        vehicle_types=vehicle_types,
        statuses=ALLOWED_STATUSES,
        message=message,
        error=error_msg,
    )


@app.route("/admin/vehicle-types/add", methods=["POST"])
def add_vehicle_type():
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    ok, err = _invoke("add_vehicle_type", _get_role(), extra_args=[name, description])
    if not ok:
        return _redirect_vehicles(error=err or "Không thể thêm loại xe.")
    return _redirect_vehicles(message="Đã thêm loại xe.")


@app.route("/admin/vehicle-types/<int:type_id>/delete", methods=["POST"])
def delete_vehicle_type(type_id: int):
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    ok, err = _invoke("delete_vehicle_type", _get_role(), extra_args=[type_id])
    if not ok:
        return _redirect_vehicles(error=err or "Không thể xóa loại xe.")
    return _redirect_vehicles(message="Đã xóa loại xe.")


def _extract_vehicle_form():
    return {
        "name": (request.form.get("name") or "").strip(),
        "license_plate": (request.form.get("license_plate") or "").strip(),
        "seats": request.form.get("seats", type=int) or 4,
        "type_id": request.form.get("type_id", type=int),
        "daily_price": request.form.get("daily_price", type=float) or 0.0,
        "status": (request.form.get("status") or "Available").strip(),
    }


@app.route("/admin/vehicles/add", methods=["POST"])
def add_vehicle():
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    payload = _extract_vehicle_form()
    ok, err = _invoke("add_vehicle", _get_role(), payload=payload)
    if not ok:
        return _redirect_vehicles(error=err or "Không thể thêm xe.")
    return _redirect_vehicles(message="Đã thêm xe mới.")


@app.route("/admin/vehicles/<int:vehicle_id>/edit", methods=["POST"])
def edit_vehicle(vehicle_id: int):
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    payload = _extract_vehicle_form()
    ok, err = _invoke("update_vehicle", _get_role(), payload=payload, extra_args=[vehicle_id])
    if not ok:
        return _redirect_vehicles(error=err or "Không thể cập nhật xe.")
    return _redirect_vehicles(message="Đã cập nhật thông tin xe.")


@app.route("/admin/vehicles/<int:vehicle_id>/status", methods=["POST"])
def update_vehicle_status(vehicle_id: int):
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    status = (request.form.get("status") or "").strip()
    if status not in ALLOWED_STATUSES:
        return _redirect_vehicles(error="Trạng thái xe không hợp lệ.")

    ok, err = _invoke("update_vehicle_status", _get_role(), extra_args=[vehicle_id, status])
    if not ok:
        return _redirect_vehicles(error=err or "Không thể đổi trạng thái xe.")
    return _redirect_vehicles(message="Đã cập nhật trạng thái xe.")


@app.route("/admin/vehicles/<int:vehicle_id>/delete", methods=["POST"])
def delete_vehicle(vehicle_id: int):
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    ok, err = _invoke("delete_vehicle", _get_role(), extra_args=[vehicle_id])
    if not ok:
        return _redirect_vehicles(error=err or "Không thể xóa xe.")
    return _redirect_vehicles(message="Đã xóa xe.")


@app.route("/admin/users")
def admin_users():
    return redirect(url_for("dashboard"))


@app.route("/admin/orders")
def admin_orders():
    return redirect(url_for("dashboard"))


@app.route("/admin/reports")
def admin_reports():
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)