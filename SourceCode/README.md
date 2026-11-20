# SourceCode

Mã nguồn ứng dụng được tổ chức theo kiến trúc 3 Layers trong tài liệu Stage 2:

- `presentation/`: giao diện và tiếp nhận thao tác/yêu cầu của người dùng.
- `business/`: xử lý quy tắc nghiệp vụ của hệ thống.
- `data/`: truy cập và thao tác với MySQL.

Framework đã thống nhất: **Flask + MySQL**. Không đặt toàn bộ chương trình vào một file duy nhất.

## Chạy ứng dụng

```bash
pip install -r requirements.txt
copy .env.example .env    # điền thông tin MySQL local, không commit .env
python run.py
```

Module xe (Issue #3) gồm `data/car_repository.py`, `business/vehicle_service.py`,
các template trong `presentation/templates/` và test trong `tests/`.
Xem hướng dẫn chi tiết tại `docs/VEHICLE_MODULE.md` (ở gốc repo).

Chạy test:

```bash
python -m unittest discover -s tests -v
```
