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

    # -- public customer-facing pages -------------------------------------------------------
    def test_home_renders_cars_from_service(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Toyota Vios 2023", response.get_data(as_text=True))

    def test_featured_brands_render_as_switchable_tabs(self):
        cars = [
            {**CAR, "carID": 10, "name": "VinFast VF 5"},
            {**CAR, "carID": 11, "name": "VinFast VF 3"},
            {**CAR, "carID": 12, "name": "Kia Carnival"},
            {**CAR, "carID": 13, "name": "Toyota Vios"},
            {**CAR, "carID": 14, "name": "BMW 320i"},
        ]
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=(cars, len(cars), 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types", return_value=[TYPE]):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        for brand in ("VinFast", "KIA", "Toyota", "BMW"):
            self.assertIn(">" + brand + "</button>", body)
        self.assertIn('id="brand-panel-1"', body)
        self.assertIn('id="brand-panel-4"', body)
        self.assertIn('data-brand-index="1"', body)
        self.assertIn('aria-selected="true"', body)
        self.assertIn("VINFAST VF 5", body)
        self.assertIn("VINFAST VF 3", body)
        self.assertIn("KIA CARNIVAL", body)
        self.assertIn("TOYOTA VIOS", body)
        self.assertIn("BMW 320I", body)
        self.assertNotIn("href=\"/cars?q=VinFast\"", body)

    def test_nav_vehicle_dropdown_and_car_rental_without_arrow(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types",
                          return_value=[TYPE]):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="g12-seats-toggle"', html)
        self.assertIn('id="g12-seat-dropdown"', html)
        for seats in ("4-Seater Vehicle", "7-Seater Vehicle",
                      "16-Seater Vehicle", "45-Seater Vehicle"):
            self.assertIn(seats, html)
        self.assertRegex(html, r'CAR RENTAL\s*</a>')
        self.assertNotIn('CAR RENTAL <span class="g12-chevron">', html)

    def test_customer_pages_use_booking_header_with_cart_and_account(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)), \
             patch.object(vehicle_service, "list_car_types", return_value=[TYPE]), \
             patch.object(vehicle_service, "get_vehicle", return_value=dict(CAR)):
            with self.client.session_transaction() as s:
                s["user_id"] = 8
                s["full_name"] = "Gia Ky"
                s["role"] = "CUSTOMER"
                s["rental_cart"] = [{
                    "car_id": 1, "selected": True,
                    "pickup_date": "2026-12-10", "return_date": "2026-12-12",
                    "pickup_location": "Tan Son Nhat Airport",
                    "return_location": "Tan Son Nhat Airport",
                }]
            for url in ("/", "/cars", "/cars/1"):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200, url)
                body = res.get_data(as_text=True)
                self.assertIn('class="g12-header"', body)
                self.assertIn('class="g12-header-inner"', body)
                self.assertIn("images/booking/group12_logo.svg", body)
                self.assertIn('class="g12-search-form"', body)
                self.assertIn("Search for cars...", body)
                self.assertIn('id="g12-seats-toggle"', body)
                self.assertIn('id="g12-seat-dropdown"', body)
                self.assertIn('id="g12-global-cart-count"', body)
                self.assertIn('Your cart (1 vehicles)', body)
                self.assertIn('class="g12-avatar-circle"', body)
                self.assertIn('class="g12-user-pill">Gia Ky</span>', body)
                self.assertIn('id="user-menu-dropdown"', body)
                self.assertIn('href="/logout"', body)
                self.assertIn("css/booking_header.css", body)
                self.assertIn("js/vehicle_cart.js", body)
                self.assertNotIn("g12-site-header", body)

    def test_booking_demo_vehicles_use_real_model_photos(self):
        with run.app.test_request_context():
            example = dict(CAR)
            for code, name, source, expected in (
                ("BOOK-VIOS-01", "Toyota Vios", "/static/images/booking/car_vios.svg", "/static/images/cars/toyotavios2023.webp"),
                ("BOOK-CITY-02", "Honda City", "/static/images/booking/car_city.svg", "/static/images/cars/hondacity2022.webp"),
                ("BOOK-VF5-03", "VinFast VF 5", "/static/images/booking/car_vf5.svg", "https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960"),
            ):
                example.update(code=code, name=name, pictures=source)
                self.assertEqual(run.car_image(example), expected)
                self.assertEqual(run.car_gallery(example)[0], expected)

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
        self.assertIn("No matching vehicles", response.get_data(as_text=True))

    def test_detail_increments_view_and_renders_all_fields(self):
        with patch.object(vehicle_service, "get_vehicle",
                          return_value=dict(CAR)) as get_car, \
             patch.object(vehicle_service, "list_vehicles",
                          return_value=([], 0, 1, FILTERS)):
            response = self.client.get("/cars/1")

        self.assertEqual(response.status_code, 200)
        get_car.assert_called_once_with(1, count_view=True)
        body = response.get_data(as_text=True)
        for expected in ("Toyota Vios 2023", "Vehicle information",
                         "5 seats", "850,000 ₫", "Book a ride", "Add to cart"):
            self.assertIn(expected, body)

    def test_price_filter_is_passed_to_vehicle_service(self):
        with patch.object(vehicle_service, "list_vehicles",
                          return_value=([CAR], 1, 1, FILTERS)) as listing, \
             patch.object(vehicle_service, "list_car_types", return_value=[TYPE]):
            response = self.client.get("/cars?price_min=500000&price_max=1000000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(listing.call_args[0][0].get("price_min"), "500000")
        self.assertEqual(listing.call_args[0][0].get("price_max"), "1000000")

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
