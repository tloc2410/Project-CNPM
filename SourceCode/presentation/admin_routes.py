"""Admin screens adapted from Chanh's UI to the shared Flask application."""
# UML [Admin]: HTTP screens/actions for Admin role (role checked against Users).


from functools import wraps
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from business import admin_service as service
from data.user_repository import find_user_permissions

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        if str(session.get("role") or "").upper() != "ADMIN":
            abort(403)
        permissions = find_user_permissions(user_id)
        if not permissions or str(permissions.get("role") or "").upper() != "ADMIN" or permissions.get("isLocked"):
            abort(403)
        return view(*args, **kwargs)
    return guarded


def _csrf():
    if "admin_action_csrf" not in session:
        session["admin_action_csrf"] = secrets.token_urlsafe(32)
    return session["admin_action_csrf"]


def _verify_csrf():
    expected = str(session.get("admin_action_csrf") or "")
    submitted = str(request.form.get("csrf_token") or "")
    if not expected or not secrets.compare_digest(expected, submitted):
        abort(400)


def _return(endpoint, success, error=""):
    return redirect(url_for(endpoint, **({"message": success} if not error else {"error": error})))


def _handle(action, endpoint, success):
    _verify_csrf()
    try:
        action()
        return _return(endpoint, success)
    except service.AdminError as exc:
        return _return(endpoint, success, str(exc))
    except Exception:
        from flask import current_app
        current_app.logger.exception("Admin action failed")
        return _return(endpoint, success, "Database operation failed. Check the input and try again.")


@admin_bp.route("/admin")
@admin_bp.route("/admin/dashboard")
@admin_required
def dashboard():
    vehicles, types = service.fleet()
    report = service.revenue_report()
    return render_template(
        "admin_dashboard.html", vehicles=vehicles, vehicle_types=types,
        total_vehicles=len(vehicles), total_types=len(types),
        available_vehicles=sum(str(v.get("status") or "").lower() == "available"
                               for v in vehicles),
        report=report, csrf_token=_csrf(),
    )


# UML [Admin, Car, CarType]: screens for vehicle/type management.
@admin_bp.route("/admin/vehicles")
@admin_required
def vehicles():
    vehicles, types = service.fleet()
    return render_template(
        "admin_vehicles.html", vehicles=vehicles, vehicle_types=types,
        statuses=service.CAR_STATUSES, csrf_token=_csrf(),
        report=service.revenue_report(), orders=service.list_orders(),
    )


@admin_bp.route("/admin/vehicle-types/add", methods=["POST"])
@admin_required
def add_type():
    return _handle(
        lambda: service.add_type(request.form.get("name"), request.form.get("description")),
        "admin.vehicles", "Vehicle type added.",
    )


@admin_bp.route("/admin/vehicle-types/<int:type_id>/delete", methods=["POST"])
@admin_required
def delete_type(type_id):
    return _handle(lambda: service.delete_type(type_id),
                   "admin.vehicles", "Vehicle type deleted.")


@admin_bp.route("/admin/vehicles/add", methods=["POST"])
@admin_required
def add_vehicle():
    return _handle(lambda: service.save_vehicle(request.form),
                   "admin.vehicles", "Vehicle created.")


@admin_bp.route("/admin/vehicles/<int:vehicle_id>/edit", methods=["POST"])
@admin_required
def edit_vehicle(vehicle_id):
    return _handle(lambda: service.save_vehicle(request.form, vehicle_id),
                   "admin.vehicles", "Vehicle updated.")


@admin_bp.route("/admin/vehicles/<int:vehicle_id>/status", methods=["POST"])
@admin_required
def set_vehicle_status(vehicle_id):
    return _handle(lambda: service.set_vehicle_status(vehicle_id, request.form.get("status")),
                   "admin.vehicles", "Vehicle status updated.")


@admin_bp.route("/admin/vehicles/<int:vehicle_id>/delete", methods=["POST"])
@admin_required
def delete_vehicle(vehicle_id):
    return _handle(lambda: service.delete_vehicle(vehicle_id),
                   "admin.vehicles", "Vehicle deleted.")


# UML [Admin, User]: user list and lock/unlock actions.
@admin_bp.route("/admin/users")
@admin_required
def users():
    return render_template(
        "admin_users.html", users=service.list_users(), csrf_token=_csrf()
    )


@admin_bp.route("/admin/users/<int:user_id>/toggle-lock", methods=["POST"])
@admin_required
def toggle_lock_user(user_id):
    def action():
        service.change_user_lock(user_id, session["user_id"])
    return _handle(action, "admin.users", "Account lock status updated.")


# UML [Admin, Order]: confirm and update rental-order status.
@admin_bp.route("/admin/orders")
@admin_required
def orders():
    return render_template(
        "admin_orders.html", orders=service.list_orders(), csrf_token=_csrf(),
        order_transitions=service.ORDER_TRANSITIONS,
    )


@admin_bp.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    return _handle(
        lambda: service.change_order_status(order_id, request.form.get("status")),
        "admin.orders", "Order status updated.",
    )


@admin_bp.route("/admin/reports")
@admin_required
def reports():
    vehicles, types = service.fleet()
    return render_template(
        "admin_reports.html", total_vehicles=len(vehicles),
        total_types=len(types), report=service.revenue_report(), csrf_token=_csrf(),
    )
