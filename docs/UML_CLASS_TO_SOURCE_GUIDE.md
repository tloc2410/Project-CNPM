# Group 12 Car Rental — UML Class Diagram → Source Code

**Mục đích:** tra nhanh khi thuyết trình: sơ đồ Use Case → chạy demo → sơ đồ lớp → mở mã nguồn.

- [Sơ đồ Use Case](../Diagrams/Group12_user_care.drawio)
- [Sơ đồ lớp (Class Diagram)](../Diagrams/Group12_Class_Diagram.drawio)
- [Sơ đồ database](../Diagrams/Database.drawio)

> **Quan trọng:** Class Diagram mô tả **10 lớp nghiệp vụ**. Bản Flask/MySQL hiện tại chủ yếu hiện thực chúng bằng **module Python, hàm và bảng SQL**, **không có 10 class Python** mang đúng tên UML. Khi trình bày, nói "hiện thực trách nhiệm của lớp UML" thay vì chỉ vào một hàm và khẳng định đó là một `class` Python. `Customer` và `Admin` là vai trò trong `Users.role`.

## Bảng tra nhanh — 10 lớp trên sơ đồ lớp

| Lớp UML | Mở file nào để chỉ cô? | Hàm / chức năng đã xây dựng | Dữ liệu |
| --- | --- | --- | --- |
| **User** | [auth_service.py](../SourceCode/business/auth_service.py), [user_repository.py](../SourceCode/data/user_repository.py), [password_reset_service.py](../SourceCode/business/password_reset_service.py) | `register_user()`, `login_user()`, `reset_password_with_token()`, `update_user_profile()` | `Users` |
| **Customer** | [run.py](../SourceCode/run.py), [booking_routes.py](../SourceCode/presentation/booking_routes.py) | `cars()`, `car_detail()`, `dashboard()`, `cart_add()`, `my_orders()` | Vai trò `CUSTOMER` trong `Users.role` |
| **Admin** | [admin_routes.py](../SourceCode/presentation/admin_routes.py), [admin_service.py](../SourceCode/business/admin_service.py) | `add_vehicle()`, `edit_vehicle()`, `set_vehicle_status()`, `toggle_lock_user()`, `change_order_status()` | Vai trò `ADMIN` trong `Users.role` |
| **CarType** | [admin_service.py](../SourceCode/business/admin_service.py), [vehicle_service.py](../SourceCode/business/vehicle_service.py), [admin_repository.py](../SourceCode/data/admin_repository.py) | `add_type()`, `delete_type()`, `list_car_types()` | `CarTypes` |
| **Car** | [vehicle_service.py](../SourceCode/business/vehicle_service.py), [car_repository.py](../SourceCode/data/car_repository.py), [admin_service.py](../SourceCode/business/admin_service.py) | `list_vehicles()`, `get_vehicle()`, `increment_views()`, `save_vehicle()`, `set_vehicle_status()` | `Cars` |
| **RentalCart** | [booking_service.py](../SourceCode/business/booking_service.py), [booking_routes.py](../SourceCode/presentation/booking_routes.py) | `add_to_cart()`, `remove_from_cart()`, `get_selected_cart_items()`, `cart_add()`, `cart_remove()` | Danh sách trong Flask `session` |
| **CartItem** (trên hình ghi *Cart Item*) | [booking_service.py](../SourceCode/business/booking_service.py) | `_normalize_cart_item()`, `update_cart_dates()`, `calculate_line_total()` | Mỗi mục là dictionary trong cart/session |
| **Order** | [booking_service.py](../SourceCode/business/booking_service.py), [booking_repository.py](../SourceCode/data/booking_repository.py), [admin_service.py](../SourceCode/business/admin_service.py) | `place_order()`, `cancel_order()`, `get_user_orders()`, `change_order_status()` | `Orders` |
| **OrderItem** | [booking_repository.py](../SourceCode/data/booking_repository.py), [booking_service.py](../SourceCode/business/booking_service.py) | `insert_order_item()`, `list_items_by_order_ids()`, `calculate_line_total()` | Bảng thực tế viết **`Oderitem`** (thiếu chữ *r*) |
| **Payment** | [payment_service.py](../SourceCode/business/payment_service.py), [payment_collection_service.py](../SourceCode/business/payment_collection_service.py), [payment_repository.py](../SourceCode/data/payment_repository.py) | `plan_payment()`, `payment_overview()`, `request_remaining_payment()`, `confirm_collection()` | `Payments` |

## Mở đúng hàm trong VS Code trong vài giây

1. Mở `Project-CNPM` → `SourceCode`.
2. Nhấn **Ctrl + Shift + F**, nhập **`UML [User]`**, **`UML [Car]`**, **`UML [Order]`** hoặc **`UML [Payment]`**.
3. Click kết quả: comment nằm ngay trên route/hàm hoặc ở đầu module, không cần cuộn tìm thủ công.
4. Để tìm tất cả chú thích một lần, tìm **`UML [`**. Các comment là mốc nhận diện, **không thay đổi logic**.

## Trình tự demo và trỏ source nhanh

| Trên màn hình demo | Source code để mở ngay |
| --- | --- |
| Đăng ký/đăng nhập, đổi thông tin tài khoản | `business/auth_service.py` → `register_user`, `login_user`; `run.py` → `account_update_profile` |
| Tìm xe, lọc xe, xem chi tiết | `business/vehicle_service.py` → `list_vehicles`, `get_vehicle` |
| Thêm xe vào giỏ, chọn ngày | `business/booking_service.py` → `add_to_cart`, `update_cart_dates` |
| Checkout → tạo đơn | `business/booking_service.py` → `place_order`; `data/booking_repository.py` → `insert_order_item` |
| Cọc 30%, tạo yêu cầu trả 70% | `business/payment_service.py` → `plan_payment`; `business/payment_collection_service.py` → `request_remaining_payment` |
| Admin duyệt giao dịch Pending | `presentation/booking_routes.py` → `admin_confirm_payment`; `business/payment_collection_service.py` → `confirm_collection` |
| Admin chuyển đơn sang RENTING | `business/admin_service.py` → `change_order_status`; Customer hiển thị trong `run.py` → `_account_order_group` |
| Admin thêm xe/khóa User | `business/admin_service.py` → `save_vehicle`, `change_user_lock` |

## Điểm khác thiết kế cần nói trung thực

- **Không có** các class domain Python `User`, `Customer`, `Admin`, `Car`, `RentalCart`, `CartItem`, `Order`, `OrderItem`, `Payment` đúng như trên sơ đồ; code tổ chức theo **Presentation → Business → Data**, dữ liệu được biểu diễn bằng dictionary và hàng SQL.
- Có **`PaymentPlan` dataclass** trong `business/payment_service.py`, nhưng đây là **class hỗ trợ lập kế hoạch thanh toán**, không phải toàn bộ class `Payment` trên sơ đồ.
- Sơ đồ có `CarType.updateType()`, nhưng hiện có **thêm/xóa loại xe**, chưa có thao tác cập nhật loại xe tương ứng.
- Sơ đồ có `Order.sendConfirmationEmail()`, nhưng hiện chưa triển khai email xác nhận đơn thuê (email đặt lại mật khẩu là tính năng khác).
- Thanh toán online của đồ án là **Student Demo**, không phải tích hợp cổng thu tiền thật; Admin xác nhận giao dịch mô phỏng ở chế độ demo.

## Câu diễn giải ngắn để nói với cô

> "Nhóm thiết kế 10 lớp nghiệp vụ trên sơ đồ Class Diagram. Ở bước triển khai, nhóm dùng Python Flask theo ba tầng Presentation, Business và Data. Vì vậy một lớp UML như **Order** được hiện thực bằng hàm `place_order` trong `booking_service.py`, hàm thao tác bảng `Orders` trong `booking_repository.py` và các route giao diện. Nhóm đã đánh dấu comment `UML [Order]` trong source code để đối chiếu trực tiếp khi thuyết trình."

**Sau khi lấy code mới:** chạy `py -m pytest Test -v` tại `SourceCode` để kiểm tra.
