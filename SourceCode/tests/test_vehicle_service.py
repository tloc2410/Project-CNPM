import unittest
from unittest.mock import patch

from mysql.connector import IntegrityError

from business import vehicle_service as service
from data import car_repository as repo


VALID_FORM = {
    "code": "sedan-09",
    "name": "Toyota Vios 2024",
    "type_id": "1",
    "seats": "5",
    "price": "850000",
    "status": "available",
    "pictures": "sedan.svg",
    "description": "Xe mai 2024, bao hanh chinh hang.",
}

CAR_ROW = {
    "carID": 1,
    "TypeID": 1,
    "code": "SEDAN-01",
    "name": "Toyota Vios 2023",
    "pictures": "sedan.svg",
    "description": "Xe cong ty",
    "numberOfSeats": 5,
    "pricePerDay": 850000.0,
    "status": "available",
    "numberOfViews": 10,
    "typeName": "Sedan",
    "rentalCount": 3,
}


class NormalizeFiltersTests(unittest.TestCase):
    def test_defaults(self):
        filters = service.normalize_filters({})
        self.assertEqual(filters["sort"], "newest")
        self.assertEqual(filters["page"], 1)
        self.assertIsNone(filters["type_id"])
        self.assertIsNone(filters["seats_min"])

    def test_sanitizes_values(self):
        filters = service.normalize_filters({
            "q": "  Toyota  ",
            "type_id": "2",
            "seats_min": "1",
            "seats_max": "999",
            "sort": "price_asc",
            "status": "RENTED",
            "page": "-5",
        })
        self.assertEqual(filters["keyword"], "Toyota")
        self.assertEqual(filters["type_id"], 2)
        self.assertEqual(filters["seats_min"], 2)
        self.assertEqual(filters["seats_max"], 55)
        self.assertEqual(filters["sort"], "price_asc")
        self.assertEqual(filters["status"], "rented")
        self.assertEqual(filters["page"], 1)

    def test_invalid_sort_and_non_numeric_type_are_ignored(self):
        filters = service.normalize_filters({
            "type_id": "abc", "sort": "drop-table", "page": "many"
        })
        self.assertIsNone(filters["type_id"])
        self.assertEqual(filters["sort"], "newest")
        self.assertEqual(filters["page"], 1)

    def test_seats_range_is_swapped_when_reversed(self):
        filters = service.normalize_filters({"seats_min": "8", "seats_max": "4"})
        self.assertEqual((filters["seats_min"], filters["seats_max"]), (4, 8))


class CarFormValidationTests(unittest.TestCase):
    def test_valid_form(self):
        with patch.object(repo, "code_exists", return_value=False), \
             patch.object(repo, "car_type_exists", return_value=True):
            data, errors = service.validate_car_form(VALID_FORM)

        self.assertEqual(errors, {})
        self.assertEqual(data["code"], "SEDAN-09")
        self.assertEqual(data["seats"], 5)
        self.assertEqual(data["price"], 850000.0)
        self.assertEqual(data["pictures"], "sedan.svg")

    def test_missing_and_invalid_fields(self):
        with patch.object(repo, "car_type_exists", return_value=False):
            data, errors = service.validate_car_form({
                "code": "", "name": "", "type_id": "x",
                "seats": "1", "price": "-5", "status": "unknown",
            })

        for field in ("code", "name", "type_id", "seats", "price", "status"):
            self.assertIn(field, errors)

    def test_duplicate_code_is_rejected(self):
        with patch.object(repo, "code_exists", return_value=True), \
             patch.object(repo, "car_type_exists", return_value=True):
            _, errors = service.validate_car_form(VALID_FORM)
        self.assertIn("code", errors)

    def test_history_of_duplicate_code_check_excludes_edited_car(self):
        with patch.object(repo, "code_exists", return_value=False) as exists, \
             patch.object(repo, "car_type_exists", return_value=True):
            service.validate_car_form(VALID_FORM, exclude_id=7)
        exists.assert_called_once_with("SEDAN-09", 7)


class CarUseCaseTests(unittest.TestCase):
    def test_detail_increments_view_once(self):
        with patch.object(repo, "get_car_by_id", return_value=dict(CAR_ROW)), \
             patch.object(repo, "increment_views", return_value=True) as inc:
            car = service.get_vehicle(1, count_view=True)

        inc.assert_called_once_with(1)
        self.assertEqual(car["numberOfViews"], 11)

    def test_detail_without_count_does_not_touch_database(self):
        with patch.object(repo, "get_car_by_id", return_value=dict(CAR_ROW)), \
             patch.object(repo, "increment_views") as inc:
            car = service.get_vehicle(1)
        inc.assert_not_called()
        self.assertEqual(car["numberOfViews"], 10)

    def test_create_reports_database_unique_error(self):
        with patch.object(service, "validate_car_form", return_value=({"code": "X"}, {})), \
             patch.object(repo, "create_car", side_effect=IntegrityError("duplicate")):
            success, message, errors = service.create_vehicle(VALID_FORM)
        self.assertFalse(success)
        self.assertIn("code", errors)
        self.assertTrue(message)

    def test_delete_reports_foreign_key_conflict(self):
        with patch.object(repo, "get_car_by_id", return_value=CAR_ROW), \
             patch.object(repo, "delete_car", side_effect=IntegrityError("fk")):
            success, message = service.delete_vehicle(1)
        self.assertFalse(success)
        self.assertIn("đơn thuê", message)

    def test_delete_missing_car(self):
        with patch.object(repo, "get_car_by_id", return_value=None):
            success, message = service.delete_vehicle(999)
        self.assertFalse(success)
        self.assertIn("Không tìm thấy", message)

    def test_invalid_status_is_rejected(self):
        with patch.object(repo, "update_car_status") as update:
            success, _ = service.set_vehicle_status(1, "DROP TABLE")
        self.assertFalse(success)
        update.assert_not_called()

    def test_out_of_range_page_falls_back_to_last_page(self):
        with patch.object(repo, "count_cars", return_value=0), \
             patch.object(repo, "search_cars", return_value=[]) as search:
            cars, total, pages, filters = service.list_vehicles({"page": "999"})

        self.assertEqual((cars, total, pages), ([], 0, 1))
        self.assertEqual(filters["page"], 1)
        self.assertEqual(search.call_args.kwargs["offset"], 0)


class CarTypeTests(unittest.TestCase):
    def test_type_with_cars_cannot_be_deleted(self):
        with patch.object(repo, "get_car_type", return_value={"typeId": 1}), \
             patch.object(repo, "count_cars_for_type", return_value=3), \
             patch.object(repo, "delete_car_type") as delete:
            success, message = service.delete_car_type(1)
        self.assertFalse(success)
        delete.assert_not_called()
        self.assertIn("đang có xe", message)

    def test_empty_type_can_be_deleted(self):
        with patch.object(repo, "get_car_type", return_value={"typeId": 1}), \
             patch.object(repo, "count_cars_for_type", return_value=0), \
             patch.object(repo, "delete_car_type", return_value=True):
            success, _ = service.delete_car_type(1)
        self.assertTrue(success)


class AdminPermissionTests(unittest.TestCase):
    def test_admin_role_from_database_is_required(self):
        with patch.object(service, "find_user_permissions",
                          return_value={"role": "ADMIN", "isLocked": 0}):
            self.assertTrue(service.is_admin(1))
        with patch.object(service, "find_user_permissions",
                          return_value={"role": "CUSTOMER", "isLocked": 0}):
            self.assertFalse(service.is_admin(1))

    def test_locked_admin_is_denied(self):
        with patch.object(service, "find_user_permissions",
                          return_value={"role": "ADMIN", "isLocked": 1}):
            self.assertFalse(service.is_admin(1))

    def test_missing_session_or_database_error_is_denied(self):
        with patch.object(service, "find_user_permissions",
                          side_effect=RuntimeError("DB down")):
            self.assertFalse(service.is_admin(1))
        self.assertFalse(service.can_manage_vehicles({}))


if __name__ == "__main__":
    unittest.main()
