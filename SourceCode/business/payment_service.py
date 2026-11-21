try:
    from data.payment_repository import create_payment
except ImportError:
    from SourceCode.data.payment_repository import create_payment

ALLOWED_METHODS = {
    "cash_on_pickup": "Tiền mặt khi nhận xe",
    "online_sim": "Trực tuyến (chế độ mô phỏng)",
}
ALLOWED_SIM_OUTCOMES = {"success", "failed"}


def process_payment(order_id, amount, method, sim_outcome="success"):
    if not order_id:
        return False, "Thiếu thông tin đơn hàng."

    if method not in ALLOWED_METHODS:
        return False, "Phương thức thanh toán không hợp lệ."

    if method == "cash_on_pickup":
        status = "Pending"
        payment_id = create_payment(order_id, amount, method, status)
        return True, f"Đã ghi nhận thanh toán tiền mặt khi nhận xe (Mã GD #{payment_id})."

    outcome = sim_outcome if sim_outcome in ALLOWED_SIM_OUTCOMES else "success"
    if outcome == "success":
        status = "Paid"
        payment_id = create_payment(order_id, amount, method, status)
        return True, f"Thanh toán trực tuyến mô phỏng thành công (Mã GD #{payment_id})."

    status = "Failed"
    create_payment(order_id, amount, method, status)
    return False, "Thanh toán trực tuyến mô phỏng thất bại. Đơn hàng cần được kiểm tra/rollback."