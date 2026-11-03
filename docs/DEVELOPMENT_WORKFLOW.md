# Quy trình làm việc chung – Group 12 Car Rental

## 1. Nguyên tắc chung

- Dùng chung repository `tloc2410/Project-CNPM`.
- Nhánh `main` là phiên bản ổn định; không commit trực tiếp lên `main`.
- Mỗi thành viên làm trên branch riêng theo module.
- Mọi thay đổi đưa vào `main` thông qua Pull Request (PR) và được ít nhất một thành viên khác kiểm tra.
- Không tự tạo một database/schema riêng khác với schema nhóm đã thống nhất.

## 2. Branch đề xuất

- `feature/account`: Member 1 – Account & Authentication.
- `feature/vehicle`: Member 2 – Vehicle Management.
- `feature/booking`: Member 3 – Rental Cart & Booking.
- `feature/payment-admin`: Member 4 – Payment & Admin Orders.
- `feature/database-schema`: thay đổi cấu trúc Database (cần phối hợp cả nhóm).

Tạo branch mới từ `main) mới nhất. Trước khi làm việc, cập nhật branch của mình với thay đổi mới nhất từ `main`.

## 3. Quy trình code

1. Mở Issue được giao và đọc checklist.
2. Chuyển Issue sang In progress trên GitHub Projects.
3. Tạo/chuyển sang branch đúng module.
4. Code và kiểm tra trên máy cá nhân.
5. Commit thay đổi với nội dung rõ ràng, ví dụ: `Add car search endpoint`.
6. Push branch lên GitHub.
7. Tạo Pull Request về `main`, ghi rõ Issue liên quan (ví dụ `Closes #3`).
8. Thành viên khác kiểm tra; chỉ merge khi đã chạy thử và không gây lỗi module khác.
9. Sau khi merge, cập nhật branch cá nhân từ `main`.

## 4. Quy trình SQL và Database

- `Database/schema.sql` là bản chuẩn để tạo cấu trúc database mới.
- `Database/sample_data.sql` chứa dữ liệu giả lập để mọi thành viên chạy thử.
- Khi thay đổi bảng/cột/khóa/quan hệ, không sửa database cá nhân rồi bỏ đó. Phải cập nhật file SQL tương ứng và gửi PR.
- Ghi thay đổi cấu trúc theo thứ tự trong `Database/migrations/`, ví dụ `001_create_users.sql`, `002_add_car_status.sql`.
- Trước khi merge thay đổi SQL, thành viên khác cần kiểm tra và chạy thử trên database test.
- Không commit mật khẩu, file `.env`, dữ liệu khách hàng thật hoặc thông tin thanh toán nhạy cảm.
- Mỗi thành viên tạo database local theo hướng dẫn trong `Database/README.md`, sau đó chạy cùng schema và sample data của nhóm.

## 5. Tránh xung đột code

- Không để hai người cùng sửa một file trong cùng thời điểm nếu có thể tránh.
- Khi cần sửa file dùng chung (cấu hình, database schema, route chung), báo nhóm trước.
- Nếu Git báo conflict, không chọn giữ toàn bộ một phía theo cảm tính; cùng xem từng phần và chạy lại chức năng liên quan.
- Không đưa file database dump chứa dữ liệu thật lên GitHub.

## 6. Quy ước hoàn thành một Issue

Một Issue chỉ chuyển sang Done khi:
- Chức năng đã được code.
- Đã kết nối đúng database nếu chức năng có dùng dữ liệu.
- Đã kiểm tra trường hợp thành công và trường hợp lỗi cơ bản.
- Code đã được review và merge vào `main`.
- Có ghi chú hoặc ảnh minh chứng cần thiết.
