# Quy trình làm việc chung – Group 12 Car Rental

## 1. Nguyên tắc chung

- Dùng chung repository `tloc2410/Project-CNPM`.
- Nhánh `main` là phiên bản ổn định; không commit trực tiếp lên `main`.
- Mỗi thành viên làm trên branch riêng theo module.
- Mọi thay đổi đưa vào `main` thông qua Pull Request (PR) và được ít nhất một thành viên khác kiểm tra.
- Không tự tạo một database/schema khác với thiết kế đã thống nhất của nhóm.

## 2. Branch đề xuất

- `feature/account`: Member 1 – Account & Authentication.
- `feature/vehicle`: Member 2 – Vehicle Management.
- `feature/booking`: Member 3 – Rental Cart & Booking.
- `feature/payment-admin`: Member 4 – Payment & Admin Orders.

Tạo branch mới từ `main` mới nhất. Trước khi làm việc, cập nhật branch của mình với thay đổi mới nhất từ `main`.

## 3. Quy trình code và SQL

1. Mở Issue được giao và đọc checklist.
2. Tạo/chuyển sang branch phù hợp.
3. Viết code hoặc file SQL trong repository.
4. Chạy thử trên máy cá nhân bằng MySQL Workbench (đối với SQL).
5. Commit với nội dung rõ ràng.
6. Push branch lên GitHub.
7. Tạo Pull Request về `main`, ghi rõ Issue liên quan.
8. Thành viên khác kiểm tra; chỉ merge khi đã chạy thử và không gây lỗi phần khác.
9. Sau khi merge, các thành viên lấy phiên bản mới nhất từ `main`.

## 4. Quản lý file SQL

- Thư mục `Database/` là nơi lưu các file SQL do nhóm tạo.
- Nhóm tự thống nhất tên file và cách chạy theo thứ tự.
- Chỉ có một thiết kế schema chuẩn do cả nhóm thống nhất; không tự ý tạo các phiên bản cấu trúc khác nhau.
- Trước khi thay đổi bảng/cột/khóa/quan hệ, thảo luận với nhóm và chạy thử trên database test.
- Mỗi thành viên có MySQL local riêng; GitHub chỉ đồng bộ file SQL, không tự đồng bộ dữ liệu MySQL đang chạy.
- Không commit mật khẩu, file `.env`, dữ liệu khách hàng thật hoặc thông tin thanh toán nhạy cảm.

## 5. Tránh xung đột

- Không để hai người cùng sửa một file trong cùng thời điểm nếu có thể tránh.
- Khi cần sửa file dùng chung, báo nhóm trước.
- Nếu Git báo conflict, cùng xem từng phần và chạy lại chức năng liên quan.
- Không đưa file database dump chứa dữ liệu thật lên GitHub.

## 6. Quy ước hoàn thành

Một công việc chỉ chuyển sang Done khi:
- Chức năng/file đã được tạo.
- Đã kiểm tra trên máy cá nhân.
- Code đã được review và merge vào `main`.
- Có ghi chú hoặc minh chứng cần thiết.
