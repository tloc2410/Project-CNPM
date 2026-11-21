from data.order_repository import get_all_orders_with_customer, update_order_status

ALLOWED_STATUSES = {"Pending", "Confirmed", "Renting", "Completed", "Cancelled"}


def _is_admin(role):
    return isinstance(role, str) and role.strip().upper() == "ADMIN"


def list_orders_for_admin(role):
    if not _is_admin(role):
        return False, "Bạn không có quyền truy cập trang quản lý đơn hàng.", []

    orders = get_all_orders_with_customer()
    return True, None, orders


def change_order_status(role, order_id, new_status):
    if not _is_admin(role):
        return False, "Bạn không có quyền cập nhật trạng thái đơn hàng."

    status_clean = (new_status or "").strip()
    if status_clean not in ALLOWED_STATUSES:
        return False, "Trạng thái đơn hàng không hợp lệ."

    updated = update_order_status(order_id, status_clean)
    if not updated:
        return False, f"Không tìm thấy đơn hàng #{order_id}."

    return True, f"Đã cập nhật đơn hàng #{order_id} sang trạng thái '{status_clean}'."