import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("mysql", MagicMock())
sys.modules.setdefault("mysql.connector", MagicMock())
sys.modules.setdefault("dotenv", MagicMock(load_dotenv=lambda *a, **kw: None))

from SourceCode.business.order_service import change_order_status, list_orders_for_admin


class TestOrderService(unittest.TestCase):
    """Kiểm thử đơn vị cho nghiệp vụ quản lý đơn hàng của Admin."""

    # 1. Abnormal: Không phải Admin không được xem danh sách đơn hàng
    @patch("SourceCode.business.order_service.get_all_orders")
    def test_non_admin_cannot_list_orders(self, mock_get_all):
        ok, msg, orders = list_orders_for_admin("CUSTOMER")

        self.assertFalse(ok)
        self.assertEqual(orders, [])
        self.assertIn("quyền", msg.lower())
        mock_get_all.assert_not_called()

    # 2. Normal: Admin xem danh sách đơn hàng hợp lệ
    @patch("SourceCode.business.order_service.get_all_orders", return_value=[{"oderID": 1}])
    def test_admin_can_list_orders(self, mock_get_all):
        ok, msg, orders = list_orders_for_admin("ADMIN")

        self.assertTrue(ok)
        self.assertEqual(msg, "")
        self.assertEqual(len(orders), 1)
        mock_get_all.assert_called_once()

    # 3. Normal: Admin chuyển trạng thái hợp lệ New -> Confirmed
    @patch("SourceCode.business.order_service.update_order_status", return_value=True)
    @patch("SourceCode.business.order_service.get_order_by_id", return_value={"oderID": 10, "status": "New"})
    def test_admin_valid_status_transition(self, mock_get_order, mock_update):
        ok, msg = change_order_status("ADMIN", 10, "Confirmed")

        self.assertTrue(ok)
        self.assertIn("Confirmed", msg)
        mock_update.assert_called_once_with(10, "Confirmed")

    # 4. Abnormal: Chuyển trạng thái sai luồng Cancelled -> Confirmed
    @patch("SourceCode.business.order_service.update_order_status")
    @patch("SourceCode.business.order_service.get_order_by_id", return_value={"oderID": 10, "status": "Cancelled"})
    def test_invalid_status_transition_rejected(self, mock_get_order, mock_update):
        ok, msg = change_order_status("ADMIN", 10, "Confirmed")

        self.assertFalse(ok)
        self.assertIn("không thể chuyển", msg.lower())
        mock_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()