import unittest
from unittest.mock import patch

from business import vehicle_service as service
from data import car_repository as repo


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

    def test_out_of_range_page_falls_back_to_last_page(self):
        with patch.object(repo, "count_cars", return_value=0), \
             patch.object(repo, "search_cars", return_value=[]) as search:
            cars, total, pages, filters = service.list_vehicles({"page": "999"})

        self.assertEqual((cars, total, pages), ([], 0, 1))
        self.assertEqual(filters["page"], 1)
        self.assertEqual(search.call_args.kwargs["offset"], 0)

if __name__ == "__main__":
    unittest.main()
