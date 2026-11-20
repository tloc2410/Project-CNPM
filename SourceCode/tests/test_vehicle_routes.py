import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

import run
from business import vehicle_service


CAR = {
    "carID": 1,
    "TypeID": 1,
    "code": "SEDAN-01",
    "name": "Toyota Vios 2023",
    "pictures": "sedan.svg",
    "description": "Xe test",
    "numberOfSeats": 5,
    "pricePerDay": 850000.0,
    "status": "available",
    "numberOfViews": 10,
    "typeName": "Sedan",
    "rentalCount": 3,
}

TYPE = {"typeId": 1, "typeName": "Sedan", "description": "Xe 5 cho"}
FILTERS = vehicle_service.normalize_filters({})


class VehicleRouteTests(unittest.TestCase):
    def setUp(self):
        run.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = run.app.test_client()

        # By default every request sees a non-admin visitor.
        patcher = patch.object(
            vehicle_service, "can_manage_vehicles", return_value=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _as_admin(self):
        patcher = patch.object(
            vehicle_service, "can_manage_vehicles", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- public pages -------------------------------------------------------
    def test_home_renders_cars_from_service(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Toyota Vios 2023", response.get_data(as_text=True))

    def test_cars_page_passes_filters_to_service(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)) as listing, \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.get("/cars?q=Toyota&sort=price_asc")

        self.assertEqual(response.status_code, 200)
        request_args = listing.call_args[0][0]
        self.assertEqual(request_args.get("q"), "Toyota")
        self.assertEqual(request_args.get("sort"), "price_asc")
        self.assertIn("Toyota Vios 2023", response.get_data(as_text=True))

    def test_no_match_shows_empty_state(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([], 0, 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types", return_value=[]):
            response = self.client.get("/cars?q=khong-ton-tai")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Không tìm thấy xe", response.get_data(as_text=True))

    def test_detail_increments_view_and_renders_all_fields(self):
        with patch.object(vehicle_service, "get_vehicle",
                          return_value=dict(CAR)) as get_car, \
             patch.object(vehicle_service, "list_vehicles",
                          return_value=([], 0, 1, FILTERS)):
            response = self.client.get("/cars/1")

        self.assertEqual(response.status_code, 200)
        get_car.assert_called_once_with(1, count_view=True)
        body = response.get_data(as_text=True)
        for expected in ("SEDAN-01", "Toyota Vios 2023", "Sedan",
                         "Available", "Lượt xem", "Lượt thuê"):
            self.assertIn(expected, body)

    def test_missing_car_returns_404(self):
        with patch.object(vehicle_service, "get_vehicle", return_value=None):
            response = self.client.get("/cars/999")
        self.assertEqual(response.status_code, 404)

    # -- admin permission ---------------------------------------------------
    def test_admin_area_denied_for_anonymous_user(self):
        self.assertEqual(self.client.get("/admin/cars").status_code, 403)
        self.assertEqual(self.client.get("/admin/car-types").status_code, 403)
        self.assertEqual(self.client.post("/admin/cars/1/delete").status_code, 403)

    def test_admin_list_page(self):
        self._as_admin()
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.get("/admin/cars")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Quản lý xe", response.get_data(as_text=True))

    def test_admin_create_success_redirects(self):
        self._as_admin()
        with patch.object(vehicle_service, "create_vehicle",
                          return_value=(True, "Đã thêm xe #13", {})), \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.post("/admin/cars/new", data={
                "code": "SEDAN-13", "name": "Xe moi", "type_id": "1",
                "seats": "5", "price": "800000", "status": "available",
            })
        self.assertEqual(response.status_code, 302)

    def test_admin_create_invalid_form_shows_errors(self):
        self._as_admin()
        with patch.object(vehicle_service, "create_vehicle",
                          return_value=(False, "Vui lòng kiểm tra lại.",
                                        {"code": "Trùng mã xe."})), \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.post("/admin/cars/new", data={"code": "X"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Trùng mã xe.", response.get_data(as_text=True))

    def test_admin_edit_delete_and_status_routes(self):
        self._as_admin()
        with patch.object(vehicle_service, "get_vehicle", return_value=dict(CAR)), \
             patch.object(vehicle_service, "list_car_types", return_value=[TYPE]):
            edit_page = self.client.get("/admin/cars/1/edit")
        self.assertEqual(edit_page.status_code, 200)

        with patch.object(vehicle_service, "delete_vehicle",
                          return_value=(True, "Đã xóa xe thành công.")):
            deleted = self.client.post("/admin/cars/1/delete")
        self.assertEqual(deleted.status_code, 302)

        with patch.object(vehicle_service, "set_vehicle_status",
                          return_value=(True, "Đã cập nhật trạng thái.")) as status:
            changed = self.client.post("/admin/cars/1/status",
                                       data={"status": "rented"})
        self.assertEqual(changed.status_code, 302)
        status.assert_called_once_with(1, "rented")

    def test_car_type_page_and_crud_routes(self):
        self._as_admin()
        with patch.object(vehicle_service, "list_car_types_with_counts",
                          return_value=[dict(TYPE, car_count=4)]):
            response = self.client.get("/admin/car-types")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sedan", response.get_data(as_text=True))

        with patch.object(vehicle_service, "create_car_type",
                          return_value=(True, "Đã thêm loại xe mới.", {})):
            created = self.client.post("/admin/car-types",
                                       data={"type_name": "Coupe"})
        self.assertEqual(created.status_code, 302)

        with patch.object(vehicle_service, "update_car_type",
                          return_value=(True, "Đã cập nhật loại xe.", {})):
            edited = self.client.post("/admin/car-types/1/edit",
                                      data={"type_name": "Sedan"})
        self.assertEqual(edited.status_code, 302)

        with patch.object(vehicle_service, "delete_car_type",
                          return_value=(False, "Không thể xóa loại xe đang có xe.")):
            blocked = self.client.post("/admin/car-types/1/delete")
        self.assertEqual(blocked.status_code, 302)


if __name__ == "__main__":
    unittest.main()
