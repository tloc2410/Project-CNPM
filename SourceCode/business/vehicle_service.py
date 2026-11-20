"""Business rules for the vehicle module.

The presentation layer calls this module; it never talks to the repository
directly. All user input is validated here before reaching MySQL.
"""
import math
import re

from mysql.connector import IntegrityError

from data import car_repository
from data.user_repository import find_user_permissions

PAGE_SIZE = 12

CAR_STATUSES = (
    ("available", "Available"),
    ("rented", "Rented"),
    ("maintenance", "Under maintenance"),
)
_STATUS_VALUES = {value for value, _ in CAR_STATUSES}
_STATUS_LABELS = dict(CAR_STATUSES)

SORT_OPTIONS = (
    ("newest", "Mới nhất"),
    ("oldest", "Cũ nhất"),
    ("name_asc", "Tên A → Z"),
    ("price_asc", "Giá tăng dần"),
    ("price_desc", "Giá giảm dần"),
    ("popular", "Lượt xem nhiều"),
    ("rentals_desc", "Lượt thuê nhiều"),
)
_SORT_VALUES = {value for value, _ in SORT_OPTIONS}

SEAT_CHOICES = (2, 4, 5, 7, 8, 16, 29, 45)
MIN_SEATS = 2
MAX_SEATS = 55
MAX_PRICE = 1_000_000_000
ADMIN_ROLES = {"ADMIN", "ADMINISTRATOR"}

_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,49}$")
_PLATE_PATTERN = re.compile(r"^[A-Za-z0-9._/\-]+\.(png|jpe?g|webp|svg)$", re.I)


def normalize_filters(args=None):
    """Turn request arguments into safe filter values."""
    args = args or {}

    def _int(value, fallback=None):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return fallback

    keyword = str(args.get("q", "") or "").strip()[:100]

    type_id = _int(args.get("type_id"))
    if type_id is None or type_id <= 0:
        type_id = None

    seats_min = _int(args.get("seats_min"))
    seats_max = _int(args.get("seats_max"))
    if seats_min is not None:
        seats_min = min(max(seats_min, MIN_SEATS), MAX_SEATS)
    if seats_max is not None:
        seats_max = min(max(seats_max, MIN_SEATS), MAX_SEATS)
    if seats_min is not None and seats_max is not None and seats_min > seats_max:
        seats_min, seats_max = seats_max, seats_min

    status = str(args.get("status", "") or "").strip().lower()
    if status not in _STATUS_VALUES:
        status = None

    sort = str(args.get("sort", "") or "").strip().lower()
    if sort not in _SORT_VALUES:
        sort = "newest"

    page = _int(args.get("page"), 1) or 1
    page = min(max(page, 1), 1000)

    return {
        "keyword": keyword,
        "type_id": type_id,
        "seats_min": seats_min,
        "seats_max": seats_max,
        "status": status,
        "sort": sort,
        "page": page,
    }


def list_vehicles(args=None):
    """Return ``(cars, total, total_pages, filters)`` for the current page."""
    filters = normalize_filters(args)
    offset = (filters["page"] - 1) * PAGE_SIZE

    common = dict(
        keyword=filters["keyword"],
        type_id=filters["type_id"],
        seats_min=filters["seats_min"],
        seats_max=filters["seats_max"],
        status=filters["status"],
    )

    total = car_repository.count_cars(**common)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    # A deleted/invalid page number falls back to the last available page.
    if filters["page"] > total_pages:
        filters["page"] = total_pages
        offset = (total_pages - 1) * PAGE_SIZE

    cars = car_repository.search_cars(
        sort=filters["sort"], limit=PAGE_SIZE, offset=offset, **common
    )
    return cars, total, total_pages, filters


def get_vehicle(car_id, count_view=False):
    """Fetch one car; optionally increment its view counter in the same call."""
    car = car_repository.get_car_by_id(car_id)
    if car and count_view:
        car_repository.increment_views(car_id)
        car["numberOfViews"] = int(car.get("numberOfViews") or 0) + 1
    return car


def _clean_pictures(raw):
    value = str(raw or "")
    parts = re.split(r"[\n,]+", value)
    pictures = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith(("http://", "https://", "//", "/")):
            if len(part) > 500:
                continue
        elif not _PLATE_PATTERN.match(part) or len(part) > 255:
            continue
        if part not in pictures:
            pictures.append(part)
        if len(pictures) == 5:
            break
    return "\n".join(pictures)


def primary_picture_name(car):
    """First stored picture token, or ``None`` when the car has no image."""
    raw = str((car or {}).get("pictures") or "")
    for part in re.split(r"[\n,]+", raw):
        part = part.strip()
        if part:
            return part
    return None


def status_label(status):
    return _STATUS_LABELS.get(status, str(status or ""))


def validate_car_form(form, exclude_id=None):
    """Validate an add/edit form. Returns ``(data, errors)``."""
    form = form or {}
    errors = {}

    code = str(form.get("code", "") or "").strip().upper()
    name = str(form.get("name", "") or "").strip()
    description = str(form.get("description", "") or "").strip()[:2000]
    pictures = _clean_pictures(form.get("pictures", ""))
    status = str(form.get("status", "available") or "available").strip().lower()
    if not status:
        status = "available"

    if not code:
        errors["code"] = "Mã xe là bắt buộc."
    elif not _CODE_PATTERN.match(code):
        errors["code"] = "Mã xe dùng chữ/số, dấu '-' hoặc '_' (2-50 ký tự)."
    elif car_repository.code_exists(code, exclude_id):
        errors["code"] = "Mã xe này đã tồn tại."

    if not name:
        errors["name"] = "Tên xe là bắt buộc."
    elif len(name) > 150:
        errors["name"] = "Tên xe không được quá 150 ký tự."

    try:
        type_id = int(str(form.get("type_id", "") or "").strip())
    except (TypeError, ValueError):
        type_id = None
    if not type_id or not car_repository.car_type_exists(type_id):
        errors["type_id"] = "Vui lòng chọn loại xe hợp lệ."

    try:
        seats = int(str(form.get("seats", "") or "").strip())
    except (TypeError, ValueError):
        seats = None
    if seats is None or not MIN_SEATS <= seats <= MAX_SEATS:
        errors["seats"] = f"Số chỗ phải từ {MIN_SEATS} đến {MAX_SEATS}."

    try:
        price = round(float(str(form.get("price", "") or "").strip()), 2)
    except (TypeError, ValueError):
        price = None
    if price is None or price <= 0 or price > MAX_PRICE:
        errors["price"] = "Giá thuê/ngày phải lớn hơn 0 và không quá 1 tỷ."

    if status not in _STATUS_VALUES:
        errors["status"] = "Trạng thái không hợp lệ."

    data = {
        "code": code,
        "name": name,
        "type_id": type_id,
        "seats": seats,
        "price": price,
        "status": status,
        "pictures": pictures,
        "description": description,
    }
    return data, errors


def create_vehicle(form):
    data, errors = validate_car_form(form)
    if errors:
        return False, "Vui lòng kiểm tra lại thông tin xe.", errors

    try:
        car_id = car_repository.create_car(data)
    except IntegrityError:
        return False, "Mã xe đã tồn tại trong database.", {"code": "Trùng mã xe."}
    except Exception:
        return False, "Không thể thêm xe. Vui lòng thử lại.", {"database": "Lỗi database."}

    return True, f"Đã thêm xe #{car_id} thành công.", {}


def update_vehicle(car_id, form):
    if not car_repository.get_car_by_id(car_id):
        return False, "Không tìm thấy xe cần cập nhật.", {}

    data, errors = validate_car_form(form, exclude_id=car_id)
    if errors:
        return False, "Vui lòng kiểm tra lại thông tin xe.", errors

    try:
        car_repository.update_car(car_id, data)
    except IntegrityError:
        return False, "Mã xe đã tồn tại trong database.", {"code": "Trùng mã xe."}
    except Exception:
        return False, "Không thể cập nhật xe. Vui lòng thử lại.", {"database": "Lỗi database."}

    return True, "Đã cập nhật thông tin xe.", {}


def delete_vehicle(car_id):
    if not car_repository.get_car_by_id(car_id):
        return False, "Không tìm thấy xe cần xóa."

    try:
        car_repository.delete_car(car_id)
    except IntegrityError:
        return False, "Không thể xóa xe này vì đã có đơn thuê liên quan."
    except Exception:
        return False, "Không thể xóa xe. Vui lòng thử lại."

    return True, "Đã xóa xe thành công."


def set_vehicle_status(car_id, status):
    status = str(status or "").strip().lower()
    if status not in _STATUS_VALUES:
        return False, "Trạng thái không hợp lệ."

    try:
        updated = car_repository.update_car_status(car_id, status)
    except Exception:
        return False, "Không thể cập nhật trạng thái."

    if not updated:
        return False, "Không tìm thấy xe cần cập nhật."
    return True, f"Đã chuyển trạng thái sang {_STATUS_LABELS[status]}."


def list_car_types():
    return car_repository.get_car_types()


def list_car_types_with_counts():
    """Types enriched with the number of cars using each type."""
    result = []
    for item in car_repository.get_car_types():
        item["car_count"] = car_repository.count_cars_for_type(item["typeId"])
        result.append(item)
    return result


def validate_type_form(form, exclude_id=None):
    form = form or {}
    errors = {}
    type_name = str(form.get("type_name", "") or "").strip()[:100]
    description = str(form.get("description", "") or "").strip()[:1000]

    if not type_name:
        errors["type_name"] = "Tên loại xe là bắt buộc."
    elif car_repository.type_name_exists(type_name, exclude_id):
        errors["type_name"] = "Tên loại xe này đã tồn tại."

    return {"type_name": type_name, "description": description}, errors


def create_car_type(form):
    data, errors = validate_type_form(form)
    if errors:
        return False, "Vui lòng kiểm tra thông tin loại xe.", errors
    try:
        car_repository.create_car_type(data["type_name"], data["description"])
    except IntegrityError:
        return False, "Tên loại xe đã tồn tại.", {"type_name": "Trùng tên loại xe."}
    except Exception:
        return False, "Không thể thêm loại xe.", {"database": "Lỗi database."}
    return True, "Đã thêm loại xe mới.", {}


def update_car_type(type_id, form):
    if not car_repository.get_car_type(type_id):
        return False, "Không tìm thấy loại xe.", {}
    data, errors = validate_type_form(form, exclude_id=type_id)
    if errors:
        return False, "Vui lòng kiểm tra thông tin loại xe.", errors
    try:
        car_repository.update_car_type(
            type_id, data["type_name"], data["description"]
        )
    except IntegrityError:
        return False, "Tên loại xe đã tồn tại.", {"type_name": "Trùng tên loại xe."}
    except Exception:
        return False, "Không thể cập nhật loại xe.", {"database": "Lỗi database."}
    return True, "Đã cập nhật loại xe.", {}


def delete_car_type(type_id):
    if not car_repository.get_car_type(type_id):
        return False, "Không tìm thấy loại xe."
    if car_repository.count_cars_for_type(type_id) > 0:
        return False, "Không thể xóa loại xe đang có xe thuộc về nó."
    try:
        car_repository.delete_car_type(type_id)
    except IntegrityError:
        return False, "Không thể xóa loại xe này."
    except Exception:
        return False, "Không thể xóa loại xe. Vui lòng thử lại."
    return True, "Đã xóa loại xe."


def is_admin(user_id):
    """Check the role in MySQL, not only the value stored in the session."""
    if not user_id:
        return False
    try:
        permissions = find_user_permissions(user_id)
    except Exception:
        return False
    if not permissions:
        return False
    role = str(permissions.get("role", "") or "").strip().upper()
    return role in ADMIN_ROLES and not permissions.get("isLocked")


def can_manage_vehicles(session):
    return is_admin(session.get("user_id"))
