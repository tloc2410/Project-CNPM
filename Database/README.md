# Database – Group 12 Car Rental

## Mục đích

Đây là nơi lưu các script SQL dùng chung của cả nhóm. GitHub chỉ lưu trữ và quản lý phiên bản file SQL; mỗi thành viên cần chạy các script trên MySQL local của mình.

## Các file

- `schema.sql`: cấu trúc database chuẩn (database, tables, primary keys, foreign keys, indexes).
- `sample_data.sql`: dữ liệu giả lập để chạy thử.
- `migrations/`: các thay đổi cấu trúc theo thứ tự, không ghi đè lịch sử.

## Sáu bảng theo Data Model Stage 2

1. `Users`
2. `Cars`
3. `CarTypes`
4. `Orders`
5. `OrderItem`
6. `Payments`

Tên bảng/cột và kiểu dữ liệu chính thức phải được cả nhóm rà soát, thống nhất trước khi viết DDL hoàn chỉnh. Tài liệu hiện có một số tên cột chưa nhất quán nên không tự ý đoán hoặc tạo nhiều bản schema khác nhau.

## Quy trình khi có thay đổi SQL

1. Thảo luận thay đổi với nhóm và ghi vào Issue Database.
2. Tạo branch, ví dụ `feature/database-schema`.
3. Cập nhật `schema.sql` nếu thay đổi bản khởi tạo; đồng thời thêm một file migration mới vào `migrations/` nếu cần giữ lịch sử cập nhật.
4. Cập nhật `sample_data.sql` nếu cấu trúc dữ liệu mẫu thay đổi.
5. Chạy thử trên database test/local.
6. Gửi PR và nhờ ít nhất một thành viên khác kiểm tra.
7. Sau khi merge, các thành viên lấy SQL mới nhất và đồng bộ database local.

## Chạy SQL bằng MySQL Workbench

1. Cài MySQL Server và MySQL Workbench.
2. Mở Workbench và kết nối MySQL local.
3. Mở file `schema.sql`, nhấn Execute (tia sét).
4. Mở `sample_data.sql`, nhấn Execute.
5. Refresh mục Schemas để kiểm tra các bảng.

Nếu nhóm dùng phpMyAdmin, mở tab Import và chọn file SQL tương ứng.

## Quy tắc an toàn

- Chỉ dùng dữ liệu giả lập trong repository.
- Không commit mật khẩu hoặc file cấu hình riêng.
- Không lưu số thẻ/CVV thanh toán.
- Không tự ý sửa schema ở máy mình mà không cập nhật script SQL lên GitHub.
