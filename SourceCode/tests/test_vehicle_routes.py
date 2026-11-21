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

    # -- public pages     # -- public pages -------------------------------------------------------
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
    
    def test_admin_vehicle_routes_are_not_registered(self):
        for url in ("/admin/cars", "/admin/cars/new", "/admin/car-types"):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post("/admin/cars/1/delete").status_code, 404)


if __name__ == "__main__":
    unittest.main()
