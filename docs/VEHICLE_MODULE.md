# Vehicle Management – Module Documentation (Issue #3)

Module hiển thị và quản lý xe của Group 12 Car Rental. Code nằm trong
`SourceCode/`, tuân thủ kiến trúc 3 layer có sẵn của nhóm và dùng chung schema
`Database/group12_car_rental.sql` (không tạo database riêng).

> Branch phát triển: `feature/vehicle` (tách từ `main` theo `docs/DEVELOPMENT_WORKFLOW.md`).

## 1. Cấu trúc file

```text
SourceCode/
├── run.py                              # Thêm route khách hàng + admin, error pages
├── data/
│   ├── car_repository.py               # MỚI: mọi truy vấn Cars / CarTypes
│   └── user_repository.py              # Thêm find_user_permissions() cho backend auth
├── business/
│   └── vehicle_service.py              # MỚI: validate, lọc/sắp xếp, CRUD, phân quyền
├── presentation/
│   ├── templates/
│   │   ├── base.html                   # MỚI: layout chung + nav theo quyền
│   │   ├── home.html                   # MỚI: trang chủ
│   │   ├── cars.html                   # MỚI: danh sách + lọc + phân trang
│   │   ├── car_detail.html             # MỚI: chi tiết xe
│   │   ├── dashboard.html              # MỚI: bảng điều khiển sau đăng nhập
│   │   ├── error.html                  # MỚI: 403/404/500
│   │   ├── _car_card.html              # MỚI: card xe dùng chung
│   │   ├── _filter_form.html           # MỚI: form lọc dùng chung
│   │   └── admin/                      # MỚI: cars.html, car_form.html, car_types.html
│   └── static/
│       ├── css/vehicle.css             # MỚI: design system dùng lại màu của auth.css
│       └── images/cars/*.webp          # Ảnh xe theo từng xe + car-placeholder.svg
├── tests/
│   ├── test_vehicle_service.py         # MỚI: unit test nghiệp vụ
│   └── test_vehicle_routes.py          # MỚI: test Flask routes với mock
└── .env.example                        # MỚI: cấu hình MySQL/Flask (không commit .env)
Database/
└── sample_data_vehicles.sql            # MỚI: 6 loại xe + 12 xe mẫu, chạy được nhiều lần
.github/workflows/vehicle-tests.yml     # MỚI: chạy unittest trên mỗi PR/push
docs/VEHICLE_MODULE.md                  # MỚI: tài liệu này
```

## 2. Cài đặt và chạy

```bash
# 1) Tạo database theo schema chung của nhóm
mysql -u root -p < Database/group12_car_rental.sql
mysql -u root -p < Database/sample_data_vehicles.sql   # dữ liệu mẫu (tùy chọn)

# 2) Cấu hình môi trường
cd SourceCode
cp .env.example .env      # Windows: copy .env.example .env
# Sửa DB_USER / DB_PASSWORD / DB_PORT / SECRET_KEY cho máy bạn

# 3) Cài dependency và chạy
pip install -r requirements.txt
python run.py
```

Mặc định `DB_PORT=3307` (theo `data/database.py` cũ). Truy cập:
`http://127.0.0.1:5000/`.

Để tạo tài khoản Admin thử nghiệm (chỉ trên database local):

```sql
UPDATE users SET role = 'ADMIN'
WHERE email = 'email_cua_ban@example.com';
```

## 3. Route

| Route | Mô tả | Quyền |
|:---|:---|:---|
| `GET /` | Trang chủ, 6 xe xem nhiều nhất + danh mục loại xe | Công khai |
| `GET /cars` | Danh sách xe: `q`, `type_id`, `seats_min`, `seats_max`, `sort`, `page` | Công khai |
| `GET /cars/<id>` | Chi tiết xe + tăng `numberOfViews` + xe cùng loại | Công khai |
| `GET /admin/cars` | Bảng quản lý xe (lọc theo `status`) | Admin |
| `GET|POST /admin/cars/new` | Thêm xe | Admin |
| `GET|POST /admin/cars/<id>/edit` | Sửa xe | Admin |
| `POST /admin/cars/<id>/delete` | Xóa xe | Admin |
| `POST /admin/cars/<id>/status` | Đổi trạng thái | Admin |
| `GET|POST /admin/car-types` | Danh sách/thêm loại xe | Admin |
| `POST /admin/car-types/<id>/edit` | Sửa loại xe | Admin |
| `POST /admin/car-types/<id>/delete` | Xóa loại xe (chỉ khi chưa có xe) | Admin |
| `GET /logout` | Đăng xuất | Đã đăng nhập |

**Phân quyền Backend:** `_require_admin()` gọi `vehicle_service.can_manage_vehicles(session)`,
hàm này đọc lại `role` và `isLocked` từ bảng `users` trong MySQL. Ngay cả khi
session bị giả mạo, backend vẫn từ chối request (403).

## 4. Đối chiếu checklist Issue #3

| Yêu cầu | Trạng thái | Vị trí |
|:---|:---:|:---|
| Trang chủ / danh sách / chi tiết theo Figma | ✅ | `home.html`, `cars.html`, `car_detail.html`, `vehicle.css` |
| Dữ liệu lấy từ MySQL, không nhập cứng | ✅ | `car_repository.py`, `sample_data_vehicles.sql` |
| Tìm kiếm theo tên xe | ✅ | `q` → `c.name / code / description / typeName LIKE` |
| Lọc theo loại xe / số chỗ | ✅ | `type_id`, `seats_min`, `seats_max` (kẹp 2–55) |
| Sắp xếp giá tăng/giảm + lượt thuê | ✅ | `sort=price_asc|price_desc|rentals_desc` (+ tên, lượt xem) |
| Chi tiết: mã, tên, ảnh, mô tả, loại, số chỗ, giá, trạng thái, lượt xem | ✅ | `car_detail.html` |
| Cập nhật lượt xem khi mở chi tiết | ✅ | `increment_views()` trong `get_vehicle(count_view=True)` |
| CRUD xe cho Admin | ✅ | `admin/cars.html`, `admin/car_form.html` |
| Quản lý loại xe | ✅ | `admin/car_types.html` |
| Trạng thái Available / Rented / Under maintenance | ✅ | `CAR_STATUSES`, route đổi status |
| Kiểm tra quyền Admin ở Backend | ✅ | `find_user_permissions()` + `_require_admin()` |
| Kết nối Cars, CarTypes, thống nhất schema issue #1 | ✅ | Dùng nguyên `group12_car_rental.sql` |
| Kiểm thử tìm thấy/không thấy, dữ liệu sai, CRUD | ✅ | `tests/` (xem mục 5) |

**Về lượt thuê:** schema hiện tại chưa có cột đếm trong `Cars`. Module tự đếm
bằng `SELECT COUNT(*) FROM Oderitem WHERE CarID = ...` (cũng hỗ trợ tên đúng
`OrderItem` nếu nhóm đổi sau này). Nếu bảng đơn hàng chưa tồn tại, giá trị
trả về là `0` và các chức năng khác vẫn chạy bình thường.

**Về Figma:** liên kết thiết kế tại `Figma/LinkFigma.md` yêu cầu đăng nhập Figma.
Giao diện được dựng theo design token đã có trong `auth.css` (cam `#f59e0b`,
slate, bo góc 12–24px, card trắng) để đồng bộ với các trang đăng nhập/đăng ký
hiện có. Có thể tinh chỉnh lại pixel theo Figma sau khi cả nhóm export asset.

## 5. Kiểm thử

Lệnh chạy (từ thư mục `SourceCode/`):

```bash
python -m unittest discover -s tests -v
```

Các case đã được automated (mock repository/DB, không cần MySQL chạy):

| Nhóm | Case | Kỳ vọng |
|:---|:---|:---|
| Lọc | defaults, làm sạch chuỗi, kẹp số chỗ, đổi sort/page không hợp lệ | Giá trị an toàn, không SQL injection |
| Validate | form hợp lệ | Trả về data chuẩn (`code` in hoa, giá làm tròn) |
| Validate | thiếu mã/tên, loại sai, số chỗ 1, giá âm, status lạ | Trả về lỗi từng field |
| Validate | trùng mã xe | Từ chối, có `errors.code` |
| Chi tiết | mở xe | `increment_views` gọi đúng 1 lần, view hiển thị +1 |
| CRUD | lỗi unique/FK từ MySQL | Thông báo thân thiện, không crash |
| CRUD | xóa loại xe còn xe | Từ chối |
| Phân quyền | role CUSTOMER / Admin bị khóa / DB lỗi | Từ chối (403) |
| Route | `/`, `/cars`, `/cars/<id>`, 404 | HTML render đúng dữ liệu service |
| Route | `/admin/*` khi chưa đăng nhập | 403 |
| Route | thêm/sửa/xóa/đổi status/thêm loại xe | Redirect + flash message |

Ngoài ra, file `.github/workflows/vehicle-tests.yml` sẽ tự chạy toàn bộ test
trên Python 3.13 mỗi khi có push/PR đụng vào `SourceCode/` hoặc `Database/`.

**Minh chứng kết quả chạy thật (local, Python 3.13.17 / Flask 3.1.3):**

```text
> python -m unittest discover -s tests -v
...
Ran 31 tests in 0.091s

OK
```

Tất cả 31 case đều pass. Máy phát triển đã cài Python 3.13 và tạo virtualenv tại
`SourceCode/.venv` (đã nằm trong `.gitignore`). Để chạy lại:

```powershell
cd SourceCode
$env:SECRET_KEY='test-only-secret-key'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Kiểm thử tay với MySQL (sau khi chạy sample data)

1. `/` → thấy 6 xe có `numberOfViews` cao nhất.
2. `/cars?q=Vios` → còn xe Toyota Vios; `/cars?q=zzzz` → hiện trạng thái "Không tìm thấy xe".
3. `/cars?type_id=2&seats_min=5&sort=price_desc` → chỉ SUV ≥ 5 chỗ, giá giảm dần.
4. Mở `/cars/3` hai lần → lượt xem tăng 2.
5. Đăng nhập Admin → `/admin/cars` → đổi status, sửa giá, thêm xe, xóa xe chưa có đơn.
6. `/admin/car-types` → xóa "Sedan" phải bị từ chối vì vẫn còn xe thuộc loại này.
7. Đăng nhập tài khoản `CUSTOMER` rồi gõ tay `/admin/cars` → trang 403.

## 6. Giới hạn biết trước

- Nút **Đặt xe** trên trang chi tiết để disabled có chủ đích: chờ module Booking
  (Issue #4) hoàn tất. Không tạo link giả.
- Ảnh xe mẫu là 12 file `.webp` theo từng xe trong `static/images/cars/`;
  `sample_data_vehicles.sql` vừa cập nhật `VALUES`, vừa có đoạn `UPDATE ... WHERE carID`
  ở cuối file để áp dụng cho database đã có sẵn (`INSERT IGNORE` không ghi đè dữ liệu cũ).
  `car-placeholder.svg` vẫn là ảnh dự phòng. Admin có thể dán URL thật hoặc tên file
  khác vào form (tối đa 5 ảnh).
- Chưa thêm index cho cột tìm kiếm; nếu dataset lớn, nên nhóm Database thống nhất
  thêm index trên `Cars(name)`, `Cars(TypeID)`, `Cars(status)` ở schema chung.
