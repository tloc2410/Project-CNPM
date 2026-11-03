# Data Layer

Đặt phần kết nối và truy cập MySQL tại đây.

Trách nhiệm:
- Đọc cấu hình kết nối từ biến môi trường.
- Thực hiện truy vấn có tham số.
- Đọc/ghi dữ liệu qua repository hoặc các hàm truy cập dữ liệu.
- Quản lý transaction khi nghiệp vụ cần nhiều thao tác phải thành công cùng nhau.

Không ghi mật khẩu database trực tiếp trong source code. Không đưa file `.env` lên GitHub.
