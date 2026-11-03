# SQL migrations

Lưu các thay đổi cấu trúc database theo thứ tự, ví dụ:

- `001_create_initial_tables.sql`
- `002_add_renter_fields.sql`
- `003_add_car_transmission_and_fuel.sql`

Mỗi migration cần:
- Có tên mô tả rõ thay đổi.
- Chạy được theo thứ tự trên database của nhóm.
- Được kiểm tra trên database test trước khi merge.
- Không chỉnh sửa migration cũ đã được các thành viên áp dụng; tạo migration mới cho thay đổi tiếp theo.
