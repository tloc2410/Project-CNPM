"""Vehicle business rules; input validation occurs before repository calls."""
import math
import re

from data import car_repository

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

    def _price(value):
        try:
            price = float(str(value).strip())
            return price if 0 <= price <= MAX_PRICE else None
        except (TypeError, ValueError):
            return None

    price_min = _price(args.get("price_min"))
    price_max = _price(args.get("price_max"))
    if price_min is not None and price_max is not None and price_min > price_max:
        price_min, price_max = price_max, price_min

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
        "price_min": price_min,
        "price_max": price_max,
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
        price_min=filters["price_min"],
        price_max=filters["price_max"],
        type_id=filters["type_id"],
        seats_min=filters["seats_min"],
        seats_max=filters["seats_max"],
        status=filters["status"],
    )

    total = car_repository.count_cars(**common)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

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


def list_car_types():
    return car_repository.get_car_types()
