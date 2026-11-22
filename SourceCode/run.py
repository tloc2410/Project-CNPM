import inspect
import os
from urllib.parse import quote
from flask import Flask, redirect, render_template, request, session

import business.vehicle_service as vehicle_service
import data.vehicle_repository as vehicle_repository  # noqa: F401


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "presentation", "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "group12-car-rental-secret-key")

ALLOWED_STATUSES = ["Available", "Rented", "Under maintenance"]
ALLOWED_ORDER_STATUSES = [
    "New",
    "Confirmed",
    "Car delivered",
    "Returned",
    "Cancelled",
]


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


def _extract_list_from_call(module_name: str, func_names: tuple, role: str = None):
    try:
        mod = __import__(module_name, fromlist=["*"])
        for fn_name in func_names:
            fn = getattr(mod, fn_name, None)
            if not callable(fn):
                continue
            sig = inspect.signature(fn)
            req_params = [
                p for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            res = fn(role) if len(req_params) >= 1 and role is not None else fn()
            if isinstance(res, list):
                return res
            if isinstance(res, tuple):
                for item in res:
                    if isinstance(item, list):
                        return item
    except Exception:
        pass
    return []


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
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    users = _extract_list_from_call(
        "data.user_repository",
        ("list_users", "get_all_users", "find_all"),
        _get_role(),
    )
    if not users:
        users = [
            {"id": 1, "full_name": "Nguyễn Văn A", "email": "nguyenvana@group12.vn", "phone": "0901111222", "address": "Quận 1, TP. HCM", "role": "Customer", "status": "Active"},
            {"id": 2, "full_name": "Trần Thị B", "email": "tranthib@group12.vn", "phone": "0902222333", "address": "Quận 7, TP. HCM", "role": "Customer", "status": "Active"},
            {"id": 3, "full_name": "Lê Văn C", "email": "levanc@group12.vn", "phone": "0903333444", "address": "Thủ Đức, TP. HCM", "role": "Customer", "status": "Active"},
            {"id": 4, "full_name": "Admin Group 12", "email": "admin@group12.vn", "phone": "0909999000", "address": "Văn phòng Group 12", "role": "Admin", "status": "Active"},
        ]

    locked_ids = set(session.get("locked_user_ids") or [])
    for idx, u in enumerate(users, start=1):
        uid = u.get("id", idx)
        u["id"] = uid
        u.setdefault("phone", "0900000000")
        u.setdefault("address", "TP. Hồ Chí Minh")
        u["is_locked"] = uid in locked_ids
        u["status"] = "Locked" if u["is_locked"] else u.get("status", "Active")

    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/toggle-lock", methods=["POST"])
def toggle_lock_user(user_id: int):
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    locked_users = set(session.get("locked_user_ids") or [])
    if user_id in locked_users:
        locked_users.remove(user_id)
        msg = f"Đã mở khóa tài khoản #{user_id}."
    else:
        locked_users.add(user_id)
        msg = f"Đã khóa tài khoản #{user_id}."

    session["locked_user_ids"] = list(locked_users)
    return redirect(f"/admin/users?message={quote(msg)}")


@app.route("/admin/orders")
def admin_orders():
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    orders = _extract_list_from_call(
        "business.order_service",
        ("list_orders_for_admin", "list_all_orders", "get_orders"),
        _get_role(),
    )
    if not orders:
        orders = [
            {"order_code": "DH00123", "customer": "Nguyễn Văn A", "vehicle": "Toyota Vios", "pickup_date": "13/10/2025", "return_date": "16/10/2025", "total": "3.600.000đ", "status": "New"},
            {"order_code": "DH00122", "customer": "Trần Thị B", "vehicle": "Hyundai Accent", "pickup_date": "12/10/2025", "return_date": "15/10/2025", "total": "4.200.000đ", "status": "Confirmed"},
            {"order_code": "DH00121", "customer": "Lê Văn C", "vehicle": "Kia Seltos", "pickup_date": "11/10/2025", "return_date": "14/10/2025", "total": "5.800.000đ", "status": "Car delivered"},
            {"order_code": "DH00120", "customer": "Phạm Thị D", "vehicle": "Mazda 3", "pickup_date": "10/10/2025", "return_date": "13/10/2025", "total": "4.500.000đ", "status": "Returned"},
        ]

    overrides = session.get("order_status_overrides") or {}
    for idx, o in enumerate(orders, start=1):
        code = str(o.get("order_code") or o.get("id") or f"DH{idx:05d}")
        o["order_code"] = code
        if code in overrides:
            o["status"] = overrides[code]

    return render_template("admin_orders.html", orders=orders)


@app.route("/admin/orders/<order_code>/status", methods=["POST"])
def update_admin_order_status(order_code: str):
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    new_status = (request.form.get("status") or "").strip()
    if new_status not in ALLOWED_ORDER_STATUSES:
        return redirect(f"/admin/orders?error={quote('Trạng thái đơn hàng không hợp lệ.')}")

    order_overrides = dict(session.get("order_status_overrides") or {})
    current_status = order_overrides.get(order_code, "New")

    if current_status == "Returned" and new_status != "Returned":
        return redirect(f"/admin/orders?error={quote('Đơn đã trả xe không thể đổi sang trạng thái khác.')}")

    order_overrides[order_code] = new_status
    session["order_status_overrides"] = order_overrides
    return redirect(f"/admin/orders?message={quote(f'Đã cập nhật đơn {order_code} sang {new_status}.')}")


@app.route("/admin/reports")
def admin_reports():
    if not _is_admin():
        return "Forbidden: Admin role required.", 403

    ok, _, vehicles, vehicle_types = _load_fleet_data()
    return render_template(
        "admin_reports.html",
        total_vehicles=len(vehicles) if ok else 0,
        total_types=len(vehicle_types) if ok else 0,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)