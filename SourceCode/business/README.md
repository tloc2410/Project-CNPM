# Business Logic Layer

Đặt phần xử lý nghiệp vụ tại đây.

Ví dụ:
- Xác thực và phân quyền.
- Tìm kiếm/lọc xe.
- Kiểm tra xe trống trong khoảng ngày thuê.
- Tính tiền thuê, phí giao xe và tiền cọc.
- Tạo/hủy/cập nhật đơn thuê theo quy tắc.
- Kiểm tra dữ liệu đầu vào.

Lớp này nhận dữ liệu từ Presentation, áp dụng quy tắc nghiệp vụ và gọi Data Layer khi cần truy cập database.
