from data import vehicle_repository as repo

ALLOWED_STATUSES = {"Available", "Rented", "Under maintenance"}


def is_admin(user_role):
    return str(user_role or "").strip().upper() == "ADMIN"


def list_admin_vehicle_data(user_role):
    if not is_admin(user_role):
        return False, "Bạn không có quyền truy cập chức năng Admin.", [], []
    vehicles = repo.get_all_vehicles()
    types = repo.get_all_vehicle_types()
    return True, "", vehicles, types


def add_vehicle(user_role, data):
    if not is_admin(user_role):
        return False, "Từ chối thao tác: yêu cầu quyền Admin."

    name = (data.get("name") or "").strip()
    license_plate = (data.get("license_plate") or "").strip()
    status = (data.get("status") or "Available").strip()
    description = (data.get("description") or "").strip()

    try:
        type_id = int(data.get("type_id"))
        daily_price = float(data.get("daily_price"))
        seats = int(data.get("seats") or 4)
    except (TypeError, ValueError):
        return False, "Loại xe, số chỗ ngồi hoặc giá thuê không hợp lệ."

    if not name or not license_plate or daily_price <= 0 or seats <= 0:
        return False, "Vui lòng nhập đầy đủ tên xe, mã/biển số, số chỗ và giá thuê hợp lệ."
    if status not in ALLOWED_STATUSES:
        return False, "Trạng thái xe không hợp lệ."

    repo.create_vehicle(
        name=name,
        license_plate=license_plate,
        type_id=type_id,
        daily_price=daily_price,
        status=status,
        seats=seats,
        description=description,
    )
    return True, "Đã thêm xe mới thành công."


def edit_vehicle(user_role, vehicle_id, data):
    if not is_admin(user_role):
        return False, "Từ chối thao tác: yêu cầu quyền Admin."

    name = (data.get("name") or "").strip()
    license_plate = (data.get("license_plate") or "").strip()
    status = (data.get("status") or "").strip()
    description = (data.get("description") or "").strip()

    try:
        vehicle_id = int(vehicle_id)
        type_id = int(data.get("type_id"))
        daily_price = float(data.get("daily_price"))
        seats = int(data.get("seats") or 4)
    except (TypeError, ValueError):
        return False, "Dữ liệu cập nhật không hợp lệ."

    if not name or not license_plate or daily_price <= 0 or seats <= 0:
        return False, "Tên xe, mã/biển số, số chỗ và giá thuê phải hợp lệ."
    if status not in ALLOWED_STATUSES:
        return False, "Trạng thái phải là Available, Rented hoặc Under maintenance."

    ok = repo.update_vehicle(
        vehicle_id=vehicle_id,
        name=name,
        license_plate=license_plate,
        type_id=type_id,
        daily_price=daily_price,
        status=status,
        seats=seats,
        description=description,
    )
    return (True, "Đã cập nhật thông tin xe.") if ok else (False, "Không tìm thấy xe cần sửa.")


def change_vehicle_status(user_role, vehicle_id, new_status):
    if not is_admin(user_role):
        return False, "Từ chối thao tác: yêu cầu quyền Admin."

    status = (new_status or "").strip()
    if status not in ALLOWED_STATUSES:
        return False, "Trạng thái xe không hợp lệ."

    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        return False, "Mã xe không hợp lệ."

    ok = repo.update_vehicle_status(vehicle_id, status)
    return (True, f"Đã cập nhật trạng thái xe sang '{status}'.") if ok else (False, "Không tìm thấy xe.")


def remove_vehicle(user_role, vehicle_id):
    if not is_admin(user_role):
        return False, "Từ chối thao tác: yêu cầu quyền Admin."

    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        return False, "Mã xe không hợp lệ."

    ok = repo.delete_vehicle(vehicle_id)
    return (True, "Đã xóa xe thành công.") if ok else (False, "Không thể xóa xe (có thể đang được liên kết dữ liệu).")


def add_vehicle_type(user_role, name, description=""):
    if not is_admin(user_role):
        return False, "Từ chối thao tác: yêu cầu quyền Admin."

    clean_name = (name or "").strip()
    if not clean_name:
        return False, "Tên loại xe không được để trống."

    repo.create_vehicle_type(clean_name, (description or "").strip())
    return True, "Đã thêm loại xe mới."


def remove_vehicle_type(user_role, type_id):
    if not is_admin(user_role):
        return False, "Từ chối thao tác: yêu cầu quyền Admin."

    try:
        type_id = int(type_id)
    except (TypeError, ValueError):
        return False, "Mã loại xe không hợp lệ."

    ok = repo.delete_vehicle_type(type_id)
    return (True, "Đã xóa loại xe.") if ok else (False, "Không thể xóa loại xe (đang có xe thuộc loại này).")