import unittest
from unittest.mock import patch

from SourceCode.business.payment_service import process_payment


class TestPaymentService(unittest.TestCase):
    """Kiểm thử đơn vị cho nghiệp vụ thanh toán theo Ch5 - Testing."""

    # 1. Normal case: Thanh toán tiền mặt khi nhận xe
    @patch("SourceCode.business.payment_service.create_payment", return_value=101)
    def test_cash_on_pickup_normal(self, mock_create_payment):
        # Setup
        order_id = 1
        amount = 500000
        method = "cash_on_pickup"

        # Call
        ok, message = process_payment(order_id, amount, method)

        # Assertion
        self.assertTrue(ok)
        self.assertIn("#101", message)
        mock_create_payment.assert_called_once_with(
            order_id, amount, method, "Pending"
        )

    # 2. Normal case: Thanh toán trực tuyến mô phỏng thành công
    @patch("SourceCode.business.payment_service.create_payment", return_value=102)
    def test_online_simulation_success(self, mock_create_payment):
        ok, message = process_payment(
            order_id=2, amount=1200000, method="online_sim", sim_outcome="success"
        )

        self.assertTrue(ok)
        self.assertIn("thành công", message.lower())
        mock_create_payment.assert_called_once_with(
            2, 1200000, "online_sim", "Paid"
        )

    # 3. Abnormal / partition case: Thanh toán trực tuyến mô phỏng thất bại
    @patch("SourceCode.business.payment_service.create_payment", return_value=103)
    def test_online_simulation_failed(self, mock_create_payment):
        ok, message = process_payment(
            order_id=3, amount=800000, method="online_sim", sim_outcome="failed"
        )

        self.assertFalse(ok)
        self.assertIn("thất bại", message.lower())
        mock_create_payment.assert_called_once_with(
            3, 800000, "online_sim", "Failed"
        )

    # 4. Abnormal / invalid input case: Thiếu order_id hoặc phương thức không hợp lệ
    @patch("SourceCode.business.payment_service.create_payment")
    def test_invalid_inputs_do_not_create_payment(self, mock_create_payment):
        ok_missing_order, _ = process_payment(None, 500000, "cash_on_pickup")
        ok_invalid_method, _ = process_payment(1, 500000, "unknown_method")

        self.assertFalse(ok_missing_order)
        self.assertFalse(ok_invalid_method)
        mock_create_payment.assert_not_called()


if __name__ == "__main__":
    unittest.main()

    import unittest
from unittest.mock import patch

from SourceCode.business.payment_service import process_payment


class TestPaymentService(unittest.TestCase):
    """Kiểm thử đơn vị cho nghiệp vụ thanh toán theo Ch5 - Testing."""

    @patch("SourceCode.business.payment_service.create_payment", return_value=101)
    def test_cash_on_pickup_normal(self, mock_create_payment):
        order_id = 1
        amount = 500000
        method = "cash_on_pickup"

        ok, message = process_payment(order_id, amount, method)

        self.assertTrue(ok)
        self.assertIn("#101", message)
        mock_create_payment.assert_called_once_with(
            order_id, amount, method, "Pending"
        )

    @patch("SourceCode.business.payment_service.create_payment", return_value=102)
    def test_online_simulation_success(self, mock_create_payment):
        ok, message = process_payment(
            order_id=2, amount=1200000, method="online_sim", sim_outcome="success"
        )

        self.assertTrue(ok)
        self.assertIn("thành công", message.lower())
        mock_create_payment.assert_called_once_with(
            2, 1200000, "online_sim", "Paid"
        )

    @patch("SourceCode.business.payment_service.create_payment", return_value=103)
    def test_online_simulation_failed(self, mock_create_payment):
        ok, message = process_payment(
            order_id=3, amount=800000, method="online_sim", sim_outcome="failed"
        )

        self.assertFalse(ok)
        self.assertIn("thất bại", message.lower())
        mock_create_payment.assert_called_once_with(
            3, 800000, "online_sim", "Failed"
        )

    @patch("SourceCode.business.payment_service.create_payment")
    def test_invalid_inputs_do_not_create_payment(self, mock_create_payment):
        ok_missing_order, _ = process_payment(None, 500000, "cash_on_pickup")
        ok_invalid_method, _ = process_payment(1, 500000, "unknown_method")

        self.assertFalse(ok_missing_order)
        self.assertFalse(ok_invalid_method)
        mock_create_payment.assert_not_called()


if __name__ == "__main__":
    unittest.main()