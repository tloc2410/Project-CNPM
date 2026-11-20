/* ============================================================================
   ĐỒ ÁN: HỆ THỐNG QUẢN LÝ XE  -  VEHICLE MANAGEMENT
   Hệ quản trị CSDL : MySQL 8.0.16+ (đã kiểm thử trên MySQL 26.10)
   Nội dung         : Bảng + ràng buộc + dữ liệu mẫu + VIEW
                      + STORED PROCEDURE + TRIGGER
   Cách chạy        : MySQL Workbench -> File -> Open SQL Script -> Execute
                      hoặc: mysql -u root -p < vehicle_management.sql

   !!! CẢNH BÁO: script DROP và tạo lại toàn bộ bảng trong database
       vehicle_management. Mọi dữ liệu cũ trong database này sẽ bị xoá.

   Quy ước đặt tên: snake_case (khớp với group12_car_rental.sql của nhóm).
   ============================================================================ */

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS vehicle_management
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE vehicle_management;

/* ----------------------------------------------------------------------------
   1. XOÁ ĐỐI TƯỢNG CŨ (theo thứ tự phụ thuộc) để chạy lại nhiều lần
   ---------------------------------------------------------------------------- */

DROP VIEW IF EXISTS vw_monthly_revenue;
DROP VIEW IF EXISTS vw_vehicle_usage;
DROP VIEW IF EXISTS vw_maintenance_cost;
DROP VIEW IF EXISTS vw_active_rentals;
DROP VIEW IF EXISTS vw_vehicle_details;

DROP TRIGGER IF EXISTS trg_vehicles_bd;
DROP TRIGGER IF EXISTS trg_maint_bu;
DROP TRIGGER IF EXISTS trg_maint_bd;
DROP TRIGGER IF EXISTS trg_maint_au;
DROP TRIGGER IF EXISTS trg_maint_ad;
DROP TRIGGER IF EXISTS trg_maint_bi;
DROP TRIGGER IF EXISTS trg_maint_ai;
DROP TRIGGER IF EXISTS trg_rentals_bu;
DROP TRIGGER IF EXISTS trg_rentals_bd;
DROP TRIGGER IF EXISTS trg_rentals_au;
DROP TRIGGER IF EXISTS trg_rentals_ad;
DROP TRIGGER IF EXISTS trg_rentals_bi;
DROP TRIGGER IF EXISTS trg_rentals_ai;

DROP TABLE IF EXISTS maintenance_items;
DROP TABLE IF EXISTS maintenance_orders;
DROP TABLE IF EXISTS rentals;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS models;
DROP TABLE IF EXISTS brands;
DROP TABLE IF EXISTS customers;

/* ============================================================================
   2. TẠO BẢNG
   ============================================================================ */

/* 2.1. Hãng xe */
CREATE TABLE brands (
    brand_id    INT           NOT NULL AUTO_INCREMENT,
    brand_name  VARCHAR(50)   NOT NULL,
    country     VARCHAR(50)   NULL,
    PRIMARY KEY (brand_id),
    UNIQUE KEY uq_brands_name (brand_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* 2.2. Dòng xe */
CREATE TABLE models (
    model_id      INT          NOT NULL AUTO_INCREMENT,
    brand_id      INT          NOT NULL,
    model_name    VARCHAR(80)  NOT NULL,
    vehicle_type  ENUM('Sedan','SUV','Hatchback','MPV','Pickup','Xe may','Xe tai') NOT NULL,
    seats         TINYINT UNSIGNED NOT NULL,
    fuel_type     ENUM('Xang','Dau','Dien','Hybrid') NOT NULL,
    PRIMARY KEY (model_id),
    UNIQUE KEY uq_models_name (brand_id, model_name),
    CONSTRAINT fk_models_brand FOREIGN KEY (brand_id) REFERENCES brands (brand_id),
    CONSTRAINT ck_models_seats CHECK (seats BETWEEN 1 AND 45)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* 2.3. Khách hàng (đồng thời là chủ xe khi được vehicles.owner_id tham chiếu) */
CREATE TABLE customers (
    customer_id    INT          NOT NULL AUTO_INCREMENT,
    full_name      VARCHAR(100) NOT NULL,
    gender         ENUM('Nam','Nu','Khac') NOT NULL,
    birth_date     DATE         NULL,
    phone          VARCHAR(15)  NOT NULL,
    email          VARCHAR(100) NULL,
    citizen_id     CHAR(12)     NULL,
    driver_license VARCHAR(20)  NULL,
    address        VARCHAR(200) NULL,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_phone (phone),
    UNIQUE KEY uq_customers_citizen (citizen_id),
    CONSTRAINT ck_customers_phone CHECK (CHAR_LENGTH(phone) BETWEEN 9 AND 15),
    CONSTRAINT ck_customers_birth CHECK (birth_date IS NULL OR birth_date >= '1900-01-01')
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* 2.4. Xe */
CREATE TABLE vehicles (
    vehicle_id       INT           NOT NULL AUTO_INCREMENT,
    plate_number     VARCHAR(12)   NOT NULL,
    model_id         INT           NOT NULL,
    owner_id         INT           NOT NULL,
    vin              CHAR(17)      NULL,
    engine_number    VARCHAR(20)   NULL,
    color            VARCHAR(20)   NOT NULL,
    manufacture_year SMALLINT UNSIGNED NOT NULL,
    purchase_date    DATE          NULL,
    odometer         INT UNSIGNED  NOT NULL DEFAULT 0,
    daily_rate       DECIMAL(12,2) NOT NULL,
    status           ENUM('San sang','Dang thue','Bao duong','Ngung su dung')
                                   NOT NULL DEFAULT 'San sang',
    note             VARCHAR(300)  NULL,
    PRIMARY KEY (vehicle_id),
    UNIQUE KEY uq_vehicles_plate (plate_number),
    UNIQUE KEY uq_vehicles_vin (vin),
    KEY ix_vehicles_status (status),
    CONSTRAINT fk_vehicles_model FOREIGN KEY (model_id) REFERENCES models (model_id),
    CONSTRAINT fk_vehicles_owner FOREIGN KEY (owner_id) REFERENCES customers (customer_id),
    CONSTRAINT ck_vehicles_year CHECK (manufacture_year BETWEEN 1950 AND 2100),
    CONSTRAINT ck_vehicles_rate CHECK (daily_rate >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* 2.5. Hợp đồng thuê xe
       rental_days / total_amount là generated column (tự tính, không nhập tay) */
CREATE TABLE rentals (
    rental_id        INT           NOT NULL AUTO_INCREMENT,
    vehicle_id       INT           NOT NULL,
    customer_id      INT           NOT NULL,
    start_date       DATE          NOT NULL,
    end_date         DATE          NOT NULL,
    pickup_odometer  INT UNSIGNED  NOT NULL,
    return_odometer  INT UNSIGNED  NULL,
    daily_rate       DECIMAL(12,2) NOT NULL,
    deposit          DECIMAL(12,2) NOT NULL DEFAULT 0,
    discount_percent DECIMAL(5,2)  NOT NULL DEFAULT 0,
    extra_fee        DECIMAL(12,2) NOT NULL DEFAULT 0,
    rental_days      INT AS (CASE WHEN DATEDIFF(end_date, start_date) = 0
                                  THEN 1 ELSE DATEDIFF(end_date, start_date) END) STORED,
    total_amount     DECIMAL(14,2) AS (ROUND(
                          (CASE WHEN DATEDIFF(end_date, start_date) = 0
                                THEN 1 ELSE DATEDIFF(end_date, start_date) END)
                          * daily_rate * (1 - discount_percent / 100) + extra_fee, 2)) STORED,
    status           ENUM('Dat truoc','Dang thue','Da tra','Da huy')
                                   NOT NULL DEFAULT 'Dang thue',
    note             VARCHAR(300)  NULL,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rental_id),
    KEY ix_rentals_vehicle (vehicle_id, start_date, end_date),
    KEY ix_rentals_status (status),
    CONSTRAINT fk_rentals_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles (vehicle_id),
    CONSTRAINT fk_rentals_customer FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    CONSTRAINT ck_rentals_dates CHECK (end_date >= start_date),
    CONSTRAINT ck_rentals_odometer CHECK (return_odometer IS NULL OR return_odometer >= pickup_odometer),
    CONSTRAINT ck_rentals_discount CHECK (discount_percent BETWEEN 0 AND 100),
    CONSTRAINT ck_rentals_money CHECK (daily_rate >= 0 AND deposit >= 0 AND extra_fee >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* 2.6. Phiếu bảo dưỡng / sửa chữa */
CREATE TABLE maintenance_orders (
    order_id           INT           NOT NULL AUTO_INCREMENT,
    vehicle_id         INT           NOT NULL,
    order_date         DATE          NOT NULL DEFAULT (CURRENT_DATE),
    service_type       ENUM('Bao duong dinh ky','Sua chua','Kiem tra','Bao hanh') NOT NULL,
    garage             VARCHAR(100)  NULL,
    description        VARCHAR(300)  NULL,
    odometer_at_service INT UNSIGNED NULL,
    labor_cost         DECIMAL(12,2) NOT NULL DEFAULT 0,
    status             ENUM('Cho xu ly','Dang thuc hien','Hoan thanh','Da huy')
                                     NOT NULL DEFAULT 'Cho xu ly',
    completion_date    DATE          NULL,
    PRIMARY KEY (order_id),
    KEY ix_maint_vehicle (vehicle_id, status),
    CONSTRAINT fk_maint_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles (vehicle_id),
    CONSTRAINT ck_maint_labor CHECK (labor_cost >= 0),
    CONSTRAINT ck_maint_complete CHECK (completion_date IS NULL OR completion_date >= order_date)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* 2.7. Vật tư / phụ tùng của phiếu bảo dưỡng */
CREATE TABLE maintenance_items (
    item_id    INT           NOT NULL AUTO_INCREMENT,
    order_id   INT           NOT NULL,
    item_name  VARCHAR(100)  NOT NULL,
    quantity   INT UNSIGNED  NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    amount     DECIMAL(14,2) AS (ROUND(quantity * unit_price, 2)) STORED,
    PRIMARY KEY (item_id),
    KEY ix_items_order (order_id),
    CONSTRAINT fk_items_order FOREIGN KEY (order_id)
        REFERENCES maintenance_orders (order_id) ON DELETE CASCADE,
    CONSTRAINT ck_items_qty CHECK (quantity > 0),
    CONSTRAINT ck_items_price CHECK (unit_price >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

/* ============================================================================
   3. DỮ LIỆU MẪU
   ============================================================================ */

/* 3.1. Hãng xe (brand_id 1..7) */
INSERT INTO brands (brand_name, country) VALUES
    ('Toyota',        'Nhật Bản'),
    ('Honda',         'Nhật Bản'),
    ('Ford',          'Mỹ'),
    ('Hyundai',       'Hàn Quốc'),
    ('VinFast',       'Việt Nam'),
    ('Mercedes-Benz', 'Đức'),
    ('Yamaha',        'Nhật Bản');

/* 3.2. Dòng xe (model_id 1..12) */
INSERT INTO models (brand_id, model_name, vehicle_type, seats, fuel_type) VALUES
    (1, 'Vios',          'Sedan',  5,  'Xang'),
    (1, 'Corolla Cross', 'SUV',    5,  'Xang'),
    (2, 'City',          'Sedan',  5,  'Xang'),
    (2, 'CR-V',          'SUV',    5,  'Xang'),
    (3, 'Ranger',        'Pickup', 5,  'Dau'),
    (4, 'Accent',        'Sedan',  5,  'Xang'),
    (5, 'VF 8',          'SUV',    5,  'Dien'),
    (5, 'VF 5',          'SUV',    5,  'Dien'),
    (6, 'C200',          'Sedan',  5,  'Xang'),
    (7, 'Exciter',       'Xe may', 2,  'Xang'),
    (2, 'SH 150i',       'Xe may', 2,  'Xang'),
    (3, 'Transit',       'MPV',    16, 'Dau');

/* 3.3. Khách hàng / chủ xe (customer_id 1..10) */
INSERT INTO customers
    (full_name, gender, birth_date, phone, email, citizen_id, driver_license, address)
VALUES
    ('Nguyễn Bá Linh',   'Nam', '2004-08-15', '0901234567', 'linh.nb@example.com',  '079204001234', 'B2-123456', 'TP. Hồ Chí Minh'),
    ('Hoàng Thế Anh',    'Nam', '2004-01-20', '0912345678', 'anh.ht@example.com',   '001204002345', 'B2-234567', 'Hà Nội'),
    ('Trần Nhật Anh',    'Nam', '2004-05-10', '0923456789', 'anh.tn@example.com',   '048204003456', 'B2-345678', 'Đà Nẵng'),
    ('Nguyễn Hữu Cường', 'Nam', '2004-12-12', '0934567890', 'cuong.nh@example.com', '040204004567', 'B2-456789', 'Nghệ An'),
    ('Phạm Khánh Hưng',  'Nam', '2004-04-03', '0945678901', 'hung.pk@example.com',  '075204005678', 'B2-567890', 'Đồng Nai'),
    ('Đào Quang Thắng',  'Nam', '2004-09-18', '0956789012', 'thang.dq@example.com', '074204006789', 'B2-678901', 'Bình Dương'),
    ('Lê Thị Mai',       'Nu',  '1998-11-22', '0967890123', 'mai.lt@example.com',   '079198007890', 'B1-789012', 'Cần Thơ'),
    ('Trần Văn Bình',    'Nam', '1990-02-05', '0978901234', 'binh.tv@example.com',  '031190008901', 'C-890123',  'Hải Phòng'),
    ('Nguyễn Thùy Dung', 'Nu',  '1995-09-09', '0989012345', 'dung.nt@example.com',  '079195009012', 'B2-901234', 'Huế'),
    ('Võ Hoàng Giang',   'Nam', '1992-07-14', '0990123456', 'giang.vh@example.com', '049192000123', 'B2-012345', 'Quảng Nam');

/* 3.4. Xe (vehicle_id 1..12) */
INSERT INTO vehicles
    (plate_number, model_id, owner_id, color, manufacture_year, purchase_date,
     odometer, daily_rate, status, note)
VALUES
    ('51A-123.45', 1,  1,  'Trắng',   2021, '2021-03-15', 45200,  800000, 'San sang',      'Xe gia đình'),
    ('51G-678.90', 2,  2,  'Đen',     2022, '2022-06-10', 31000, 1200000, 'Dang thue',     'Đang cho thuê'),
    ('30A-111.22', 3,  3,  'Bạc',     2020, '2020-09-01', 68000,  750000, 'San sang',      NULL),
    ('43A-333.44', 4,  4,  'Xám',     2023, '2023-01-20', 18500, 1400000, 'San sang',      'Đã đặt lịch thuê'),
    ('60C-555.66', 5,  5,  'Xanh',    2022, '2022-11-05', 52000, 1500000, 'Bao duong',     'Đang sửa hộp số'),
    ('29A-777.88', 6,  6,  'Đỏ',      2021, '2021-07-19', 39000,  700000, 'San sang',      NULL),
    ('30E-999.00', 7,  7,  'Trắng',   2023, '2023-04-02', 12000, 1600000, 'San sang',      'Xe điện'),
    ('51K-222.33', 8,  8,  'Xanh lá', 2023, '2023-08-25', 21000,  900000, 'Dang thue',     'Đang cho thuê'),
    ('51F-444.55', 9,  9,  'Đen',     2022, '2022-02-14', 26000, 2200000, 'San sang',      NULL),
    ('59B-666.77', 10, 10, 'Xanh',    2021, '2021-10-10', 34000,  250000, 'San sang',      'Xe máy'),
    ('59C-888.99', 11, 1,  'Trắng',   2022, '2022-05-30', 27000,  350000, 'Ngung su dung', 'Chờ thanh lý'),
    ('51B-135.79', 12, 2,  'Bạc',     2020, '2020-12-12', 95000, 1800000, 'San sang',      'Xe 16 chỗ');

/* 3.5. Hợp đồng thuê (rental_id 1..11) */
INSERT INTO rentals
    (vehicle_id, customer_id, start_date, end_date, pickup_odometer, return_odometer,
     daily_rate, deposit, discount_percent, extra_fee, status, note)
VALUES
    (2,  3,  '2026-11-10', '2026-11-15', 31000, NULL,  1200000, 2000000, 0,  0, 'Dang thue', 'Thuê 5 ngày'),
    (8,  4,  '2026-11-12', '2026-11-14', 21000, NULL,   900000, 1000000, 0,  0, 'Dang thue', NULL),
    (4,  5,  '2026-11-20', '2026-11-23', 18500, NULL,  1400000, 2000000, 5,  0, 'Dat truoc', 'Đặt trước'),
    (1,  7,  '2026-10-01', '2026-10-05', 43800, 44250,  800000, 1500000, 0,  0, 'Da tra',    NULL),
    (3,  8,  '2026-10-10', '2026-10-12', 67500, 67900,  750000, 1000000, 10, 0, 'Da tra',    'Giảm 10%'),
    (9,  9,  '2026-09-15', '2026-09-18', 25400, 25700, 2200000, 3000000, 0,  0, 'Da tra',    NULL),
    (6,  10, '2026-09-20', '2026-09-22', 38000, 38400,  700000, 1000000, 0,  0, 'Da tra',    NULL),
    (7,  1,  '2026-10-25', '2026-10-28', 11000, 11400, 1600000, 2000000, 0,  0, 'Da tra',    NULL),
    (10, 2,  '2026-11-05', '2026-11-06', 33800, 33950,  250000,  500000, 0,  0, 'Da tra',    'Thuê xe máy'),
    (12, 6,  '2026-11-18', '2026-11-20', 95000, NULL,  1800000, 2500000, 0,  0, 'Dat truoc', 'Đoàn 12 người'),
    (3,  2,  '2026-11-25', '2026-11-27', 67900, NULL,   750000, 1000000, 0,  0, 'Dat truoc', NULL);

/* 3.6. Phiếu bảo dưỡng (order_id 1..8) */
INSERT INTO maintenance_orders
    (vehicle_id, order_date, service_type, garage, description,
     odometer_at_service, labor_cost, status, completion_date)
VALUES
    (5,  '2026-11-11', 'Sua chua',          'Garage Ford Sài Gòn', 'Thay lọc dầu, kiểm tra hộp số',       52000,  500000, 'Dang thuc hien', NULL),
    (1,  '2026-10-02', 'Bao duong dinh ky', 'Toyota Bến Thành',    'Bảo dưỡng 45.000 km',                 43800,  800000, 'Hoan thanh',     '2026-10-02'),
    (3,  '2026-09-28', 'Bao duong dinh ky', 'Honda Kim Thanh',     'Thay dầu máy, lọc gió',               67000,  650000, 'Hoan thanh',     '2026-09-28'),
    (9,  '2026-10-20', 'Kiem tra',          'Mercedes Việt Nam',   'Kiểm tra tổng quát',                  25800,  300000, 'Cho xu ly',      NULL),
    (12, '2026-10-15', 'Sua chua',          'Ford An Sương',       'Sửa điều hoà',                        94500, 1200000, 'Hoan thanh',     '2026-10-15'),
    (6,  '2026-11-12', 'Bao duong dinh ky', 'Hyundai Ngọc An',     'Bảo dưỡng 40.000 km',                 39000,  700000, 'Cho xu ly',      NULL),
    (4,  '2026-11-01', 'Bao hanh',          'Honda Phước Thạnh',   'Thay cảm biến áp suất lốp (bảo hành)', 18300,       0, 'Hoan thanh',     '2026-11-01'),
    (10, '2026-10-28', 'Sua chua',          'Yamaha Town',         'Thay xích, nhông',                    33600,  350000, 'Hoan thanh',     '2026-10-28');

/* 3.7. Vật tư của phiếu bảo dưỡng */
INSERT INTO maintenance_items (order_id, item_name, quantity, unit_price) VALUES
    (1, 'Dầu động cơ 5W-30',    4, 180000),
    (1, 'Lọc dầu',              1, 250000),
    (1, 'Lọc nhiên liệu',       1, 420000),
    (2, 'Dầu máy 0W-20',        4, 200000),
    (2, 'Lọc gió',              1, 350000),
    (3, 'Dầu máy 0W-20',        4, 190000),
    (3, 'Lọc gió',              1, 320000),
    (3, 'Bugi',                 4, 150000),
    (4, 'Máy chẩn đoán lỗi',    1, 150000),
    (5, 'Gas điều hoà R134a',   2, 300000),
    (5, 'Lọc gió điều hoà',     1, 250000),
    (7, 'Cảm biến áp suất lốp', 1,      0),
    (8, 'Bộ xích nhông',        1, 450000),
    (8, 'Nhớt xích',            1,  80000);

/* ============================================================================
   4. VIEW
   ============================================================================ */

/* 4.1. Thông tin đầy đủ của xe */
CREATE OR REPLACE VIEW vw_vehicle_details AS
SELECT  v.vehicle_id,
        v.plate_number,
        b.brand_name,
        m.model_name,
        m.vehicle_type,
        m.seats,
        m.fuel_type,
        v.color,
        v.manufacture_year,
        v.odometer,
        v.daily_rate,
        v.status,
        c.full_name AS owner_name,
        c.phone     AS owner_phone
FROM vehicles  v
JOIN models    m ON m.model_id = v.model_id
JOIN brands    b ON b.brand_id = m.brand_id
JOIN customers c ON c.customer_id = v.owner_id;

/* 4.2. Hợp đồng đang hiệu lực (đặt trước + đang thuê) */
CREATE OR REPLACE VIEW vw_active_rentals AS
SELECT  r.rental_id,
        v.plate_number,
        b.brand_name,
        m.model_name,
        cu.full_name AS renter_name,
        cu.phone     AS renter_phone,
        r.start_date,
        r.end_date,
        r.rental_days,
        r.daily_rate,
        r.total_amount,
        r.status,
        DATEDIFF(r.end_date, CURRENT_DATE) AS days_left,
        CASE WHEN r.status = 'Dang thue' AND r.end_date < CURRENT_DATE
             THEN 'Qua han' ELSE 'Dung han' END AS due_status
FROM rentals   r
JOIN vehicles  v  ON v.vehicle_id   = r.vehicle_id
JOIN models    m  ON m.model_id     = v.model_id
JOIN brands    b  ON b.brand_id     = m.brand_id
JOIN customers cu ON cu.customer_id = r.customer_id
WHERE r.status IN ('Dat truoc', 'Dang thue');

/* 4.3. Chi phí từng phiếu bảo dưỡng = công + phụ tùng */
CREATE OR REPLACE VIEW vw_maintenance_cost AS
SELECT  o.order_id,
        v.plate_number,
        o.order_date,
        o.service_type,
        o.garage,
        o.status,
        o.odometer_at_service,
        o.labor_cost,
        IFNULL(SUM(i.amount), 0)               AS parts_cost,
        o.labor_cost + IFNULL(SUM(i.amount), 0) AS total_cost
FROM maintenance_orders o
JOIN vehicles          v ON v.vehicle_id = o.vehicle_id
LEFT JOIN maintenance_items i ON i.order_id = o.order_id
GROUP BY o.order_id, v.plate_number, o.order_date, o.service_type,
         o.garage, o.status, o.odometer_at_service, o.labor_cost;

/* 4.4. Tổng hợp sử dụng từng xe */
CREATE OR REPLACE VIEW vw_vehicle_usage AS
SELECT  v.vehicle_id,
        v.plate_number,
        b.brand_name,
        m.model_name,
        v.status,
        (SELECT COUNT(*) FROM rentals r
          WHERE r.vehicle_id = v.vehicle_id AND r.status = 'Da tra')      AS completed_rentals,
        (SELECT IFNULL(SUM(r.total_amount), 0) FROM rentals r
          WHERE r.vehicle_id = v.vehicle_id AND r.status = 'Da tra')      AS rental_revenue,
        (SELECT COUNT(*) FROM maintenance_orders o
          WHERE o.vehicle_id = v.vehicle_id)                              AS maintenance_orders,
        (SELECT IFNULL(SUM(o.labor_cost), 0) FROM maintenance_orders o
          WHERE o.vehicle_id = v.vehicle_id AND o.status = 'Hoan thanh')  AS labor_cost,
        (SELECT IFNULL(SUM(i.amount), 0)
           FROM maintenance_items i
           JOIN maintenance_orders o ON o.order_id = i.order_id
          WHERE o.vehicle_id = v.vehicle_id AND o.status = 'Hoan thanh')  AS parts_cost
FROM vehicles v
JOIN models   m ON m.model_id = v.model_id
JOIN brands   b ON b.brand_id = m.brand_id;

/* 4.5. Doanh thu thuê xe theo tháng (chỉ hợp đồng đã trả xe) */
CREATE OR REPLACE VIEW vw_monthly_revenue AS
SELECT  YEAR(r.start_date)  AS nam,
        MONTH(r.start_date) AS thang,
        COUNT(*)            AS so_hop_dong,
        SUM(r.rental_days)  AS tong_ngay_thue,
        SUM(r.total_amount) AS doanh_thu
FROM rentals r
WHERE r.status = 'Da tra'
GROUP BY YEAR(r.start_date), MONTH(r.start_date);

/* ============================================================================
   5. STORED PROCEDURE
   ----------------------------------------------------------------------------
   LƯU Ý QUAN TRỌNG VỀ TRANSACTION:
   Không dùng START TRANSACTION hoặc COMMIT bên trong procedure, vì lệnh
   START TRANSACTION sẽ NGẦM COMMIT transaction đang mở của người gọi
   (implicit commit), tức procedure âm thầm ghi dữ liệu dù caller muốn rollback.

   Ở đây mỗi procedure chỉ ghi bằng MỘT câu lệnh (INSERT hoặc UPDATE).
   InnoDB đã bảo đảm mỗi câu lệnh là một transaction nguyên tử, và các
   trigger chạy trong cùng câu lệnh đó, nên không cần transaction tường minh.
   Nhờ vậy có thể gọi procedure bên trong transaction của mình:
       START TRANSACTION; CALL sp_...; ROLLBACK;
   ============================================================================ */

DELIMITER $$

/* 5.1. Thêm xe mới */
DROP PROCEDURE IF EXISTS sp_add_vehicle$$
CREATE PROCEDURE sp_add_vehicle(
    IN  p_plate_number     VARCHAR(12),
    IN  p_model_id         INT,
    IN  p_owner_id         INT,
    IN  p_color            VARCHAR(20),
    IN  p_manufacture_year SMALLINT UNSIGNED,
    IN  p_daily_rate       DECIMAL(12,2),
    IN  p_odometer         INT UNSIGNED,
    IN  p_vin              CHAR(17),
    IN  p_note             VARCHAR(300),
    OUT p_vehicle_id       INT
)
BEGIN
    IF p_plate_number IS NULL OR TRIM(p_plate_number) = '' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Bien so khong duoc de trong';
    END IF;

    IF EXISTS (SELECT 1 FROM vehicles WHERE plate_number = p_plate_number) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Bien so xe da ton tai';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM models WHERE model_id = p_model_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Dong xe khong ton tai';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE customer_id = p_owner_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Chu xe khong ton tai';
    END IF;

    IF p_daily_rate < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Gia thue khong duoc am';
    END IF;

    INSERT INTO vehicles
        (plate_number, model_id, owner_id, vin, color,
         manufacture_year, odometer, daily_rate, status, note)
    VALUES
        (p_plate_number, p_model_id, p_owner_id, p_vin, p_color,
         p_manufacture_year, IFNULL(p_odometer, 0), p_daily_rate, 'San sang', p_note);

    SET p_vehicle_id = LAST_INSERT_ID();
END$$

/* 5.2. Tìm xe theo từ khoá (biển số / hãng / dòng) và trạng thái */
DROP PROCEDURE IF EXISTS sp_search_vehicles$$
CREATE PROCEDURE sp_search_vehicles(
    IN p_keyword VARCHAR(50),
    IN p_status  VARCHAR(20)
)
BEGIN
    SELECT *
    FROM vw_vehicle_details
    WHERE (p_keyword IS NULL
           OR plate_number LIKE CONCAT('%', p_keyword, '%')
           OR brand_name   LIKE CONCAT('%', p_keyword, '%')
           OR model_name   LIKE CONCAT('%', p_keyword, '%'))
      AND (p_status IS NULL OR status = p_status)
    ORDER BY plate_number;
END$$

/* 5.3. Tạo hợp đồng thuê xe */
DROP PROCEDURE IF EXISTS sp_register_rental$$
CREATE PROCEDURE sp_register_rental(
    IN  p_vehicle_id       INT,
    IN  p_customer_id      INT,
    IN  p_start_date       DATE,
    IN  p_end_date         DATE,
    IN  p_deposit          DECIMAL(12,2),
    IN  p_discount_percent DECIMAL(5,2),
    IN  p_note             VARCHAR(300),
    OUT p_rental_id        INT
)
BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_rate   DECIMAL(12,2);
    DECLARE v_odo    INT;

    IF p_start_date IS NULL OR p_end_date IS NULL OR p_end_date < p_start_date THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ngay thue khong hop le';
    END IF;

    IF IFNULL(p_discount_percent, 0) < 0 OR IFNULL(p_discount_percent, 0) > 100
       OR IFNULL(p_deposit, 0) < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Giam gia hoac tien coc khong hop le';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE customer_id = p_customer_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Khach hang khong ton tai';
    END IF;

    SELECT status, daily_rate, odometer
      INTO v_status, v_rate, v_odo
      FROM vehicles
     WHERE vehicle_id = p_vehicle_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe khong ton tai';
    END IF;

    IF v_status IN ('Bao duong', 'Ngung su dung') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe dang bao duong/ngung su dung';
    END IF;

    IF EXISTS (SELECT 1
                 FROM rentals
                WHERE vehicle_id = p_vehicle_id
                  AND status IN ('Dat truoc', 'Dang thue')
                  AND p_start_date < end_date
                  AND p_end_date   > start_date) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe da co hop dong trung thoi gian';
    END IF;

    INSERT INTO rentals
        (vehicle_id, customer_id, start_date, end_date, pickup_odometer,
         daily_rate, deposit, discount_percent, status, note)
    VALUES
        (p_vehicle_id, p_customer_id, p_start_date, p_end_date, v_odo,
         v_rate, IFNULL(p_deposit, 0), IFNULL(p_discount_percent, 0),
         CASE WHEN p_start_date <= CURRENT_DATE THEN 'Dang thue' ELSE 'Dat truoc' END,
         p_note);

    SET p_rental_id = LAST_INSERT_ID();
END$$

/* 5.4. Trả xe */
DROP PROCEDURE IF EXISTS sp_return_vehicle$$
CREATE PROCEDURE sp_return_vehicle(
    IN p_rental_id       INT,
    IN p_return_odometer INT UNSIGNED,
    IN p_extra_fee       DECIMAL(12,2),
    IN p_return_date     DATE
)
BEGIN
    DECLARE v_vehicle_id INT;
    DECLARE v_status     VARCHAR(20);
    DECLARE v_pickup     INT;
    DECLARE v_start      DATE;
    DECLARE v_date       DATE;

    SELECT vehicle_id, status, pickup_odometer, start_date
      INTO v_vehicle_id, v_status, v_pickup, v_start
      FROM rentals
     WHERE rental_id = p_rental_id;

    IF v_vehicle_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Hop dong thue khong ton tai';
    END IF;

    IF v_status <> 'Dang thue' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Chi tra xe cho hop dong Dang thue';
    END IF;

    IF p_return_odometer < v_pickup THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'So km tra < so km nhan';
    END IF;

    IF IFNULL(p_extra_fee, 0) < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phu phi khong duoc am';
    END IF;

    SET v_date = IFNULL(p_return_date, CURRENT_DATE);

    IF v_date < v_start THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ngay tra truoc ngay nhan xe';
    END IF;

    /* Một câu UPDATE duy nhất. Việc cập nhật bảng vehicles (trạng thái + số km)
       do trigger trg_rentals_au đảm nhiệm, nên vẫn nguyên tử trong cùng câu lệnh. */
    UPDATE rentals
       SET return_odometer = p_return_odometer,
           extra_fee       = IFNULL(p_extra_fee, 0),
           end_date        = v_date,
           status          = 'Da tra'
     WHERE rental_id = p_rental_id;

    SELECT * FROM rentals WHERE rental_id = p_rental_id;
END$$

/* 5.5. Huỷ hợp đồng chưa trả xe */
DROP PROCEDURE IF EXISTS sp_cancel_rental$$
CREATE PROCEDURE sp_cancel_rental(
    IN p_rental_id INT,
    IN p_reason    VARCHAR(300)
)
BEGIN
    DECLARE v_status VARCHAR(20);

    SELECT status INTO v_status FROM rentals WHERE rental_id = p_rental_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Hop dong thue khong ton tai';
    END IF;

    IF v_status = 'Da tra' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Hop dong da tra xe, khong the huy';
    END IF;

    IF v_status = 'Da huy' THEN
        SELECT 'Hop dong da bi huy truoc do' AS thong_bao;
    ELSE
        UPDATE rentals
           SET status = 'Da huy',
               note   = IFNULL(p_reason, note)
         WHERE rental_id = p_rental_id;
        SELECT CONCAT('Da huy hop dong thue #', p_rental_id) AS thong_bao;
    END IF;
END$$

/* 5.6. Tạo phiếu bảo dưỡng */
DROP PROCEDURE IF EXISTS sp_create_maintenance_order$$
CREATE PROCEDURE sp_create_maintenance_order(
    IN  p_vehicle_id         INT,
    IN  p_service_type       VARCHAR(30),
    IN  p_garage             VARCHAR(100),
    IN  p_description        VARCHAR(300),
    IN  p_odometer_at_service INT UNSIGNED,
    IN  p_labor_cost         DECIMAL(12,2),
    IN  p_status             VARCHAR(20),
    OUT p_order_id           INT
)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM vehicles WHERE vehicle_id = p_vehicle_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe khong ton tai';
    END IF;

    IF p_service_type NOT IN ('Bao duong dinh ky', 'Sua chua', 'Kiem tra', 'Bao hanh') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Loai dich vu khong hop le';
    END IF;

    IF p_status NOT IN ('Cho xu ly', 'Dang thuc hien', 'Hoan thanh', 'Da huy') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trang thai phieu khong hop le';
    END IF;

    IF p_labor_cost < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Chi phi cong khong duoc am';
    END IF;

    IF p_status = 'Hoan thanh' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu moi khong the o trang thai Hoan thanh';
    END IF;

    INSERT INTO maintenance_orders
        (vehicle_id, order_date, service_type, garage, description,
         odometer_at_service, labor_cost, status, completion_date)
    VALUES
        (p_vehicle_id, CURRENT_DATE, p_service_type, p_garage, p_description,
         p_odometer_at_service, IFNULL(p_labor_cost, 0), p_status, NULL);

    SET p_order_id = LAST_INSERT_ID();
END$$

/* 5.7. Thêm vật tư vào phiếu bảo dưỡng */
DROP PROCEDURE IF EXISTS sp_add_maintenance_item$$
CREATE PROCEDURE sp_add_maintenance_item(
    IN p_order_id   INT,
    IN p_item_name  VARCHAR(100),
    IN p_quantity   INT UNSIGNED,
    IN p_unit_price DECIMAL(12,2)
)
BEGIN
    DECLARE v_status VARCHAR(20);

    SELECT status INTO v_status FROM maintenance_orders WHERE order_id = p_order_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu bao duong khong ton tai';
    END IF;

    IF v_status IN ('Hoan thanh', 'Da huy') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu da ket thuc, khong the them vat tu';
    END IF;

    IF p_quantity <= 0 OR p_unit_price < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'So luong phai > 0 va don gia >= 0';
    END IF;

    INSERT INTO maintenance_items (order_id, item_name, quantity, unit_price)
    VALUES (p_order_id, p_item_name, p_quantity, p_unit_price);
END$$

/* 5.8. Hoàn thành phiếu bảo dưỡng */
DROP PROCEDURE IF EXISTS sp_complete_maintenance$$
CREATE PROCEDURE sp_complete_maintenance(
    IN p_order_id          INT,
    IN p_odometer_at_service INT UNSIGNED,
    IN p_completion_date   DATE
)
BEGIN
    DECLARE v_status VARCHAR(20);

    SELECT status INTO v_status FROM maintenance_orders WHERE order_id = p_order_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu bao duong khong ton tai';
    END IF;

    IF v_status IN ('Hoan thanh', 'Da huy') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu da ket thuc, khong the cap nhat';
    END IF;

    UPDATE maintenance_orders
       SET status             = 'Hoan thanh',
           completion_date    = IFNULL(p_completion_date, CURRENT_DATE),
           odometer_at_service = IFNULL(p_odometer_at_service, odometer_at_service)
     WHERE order_id = p_order_id;
END$$

/* 5.9. Báo cáo doanh thu theo tháng của một năm */
DROP PROCEDURE IF EXISTS sp_revenue_by_month$$
CREATE PROCEDURE sp_revenue_by_month(IN p_year INT)
BEGIN
    SELECT thang, so_hop_dong, tong_ngay_thue, doanh_thu
    FROM vw_monthly_revenue
    WHERE nam = p_year
    ORDER BY thang;
END$$

DELIMITER ;

/* ============================================================================
   6. TRIGGER
   ============================================================================ */

DELIMITER $$

/* 6.1. Kiểm tra khi THÊM hợp đồng thuê */
DROP TRIGGER IF EXISTS trg_rentals_bi$$
CREATE TRIGGER trg_rentals_bi
BEFORE INSERT ON rentals
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_cnt    INT DEFAULT 0;

    IF NEW.end_date < NEW.start_date THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ngay tra phai >= ngay nhan';
    END IF;

    IF NEW.return_odometer IS NOT NULL AND NEW.return_odometer < NEW.pickup_odometer THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'So km tra < so km nhan';
    END IF;

    IF NEW.status IN ('Dat truoc', 'Dang thue') THEN
        SELECT status INTO v_status FROM vehicles WHERE vehicle_id = NEW.vehicle_id;

        IF v_status IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe khong ton tai';
        END IF;

        IF v_status IN ('Bao duong', 'Ngung su dung') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe dang bao duong/ngung su dung';
        END IF;

        SELECT COUNT(*) INTO v_cnt
          FROM rentals
         WHERE vehicle_id = NEW.vehicle_id
           AND status IN ('Dat truoc', 'Dang thue')
           AND NEW.start_date < end_date
           AND NEW.end_date   > start_date;

        IF v_cnt > 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe da co hop dong trung thoi gian';
        END IF;
    END IF;
END$$

/* 6.2. Kiểm tra khi SỬA hợp đồng thuê */
DROP TRIGGER IF EXISTS trg_rentals_bu$$
CREATE TRIGGER trg_rentals_bu
BEFORE UPDATE ON rentals
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_cnt    INT DEFAULT 0;

    IF NEW.end_date < NEW.start_date THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ngay tra phai >= ngay nhan';
    END IF;

    IF NEW.return_odometer IS NOT NULL AND NEW.return_odometer < NEW.pickup_odometer THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'So km tra < so km nhan';
    END IF;

    IF NEW.status IN ('Dat truoc', 'Dang thue') THEN
        SELECT status INTO v_status FROM vehicles WHERE vehicle_id = NEW.vehicle_id;

        IF v_status IN ('Bao duong', 'Ngung su dung') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe dang bao duong/ngung su dung';
        END IF;

        SELECT COUNT(*) INTO v_cnt
          FROM rentals
         WHERE vehicle_id = NEW.vehicle_id
           AND rental_id <> NEW.rental_id
           AND status IN ('Dat truoc', 'Dang thue')
           AND NEW.start_date < end_date
           AND NEW.end_date   > start_date;

        IF v_cnt > 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe da co hop dong trung thoi gian';
        END IF;
    END IF;
END$$

/* 6.3. Đồng bộ trạng thái xe sau khi THÊM hợp đồng */
DROP TRIGGER IF EXISTS trg_rentals_ai$$
CREATE TRIGGER trg_rentals_ai
AFTER INSERT ON rentals
FOR EACH ROW
BEGIN
    IF NEW.status = 'Dang thue' THEN
        UPDATE vehicles
           SET status = 'Dang thue'
         WHERE vehicle_id = NEW.vehicle_id
           AND status NOT IN ('Bao duong', 'Ngung su dung');
    END IF;

    IF NEW.return_odometer IS NOT NULL AND NEW.return_odometer > 0 THEN
        UPDATE vehicles
           SET odometer = NEW.return_odometer
         WHERE vehicle_id = NEW.vehicle_id
           AND NEW.return_odometer > odometer;
    END IF;
END$$

/* 6.4. Đồng bộ trạng thái xe sau khi SỬA hợp đồng */
DROP TRIGGER IF EXISTS trg_rentals_au$$
CREATE TRIGGER trg_rentals_au
AFTER UPDATE ON rentals
FOR EACH ROW
BEGIN
    IF NEW.status = 'Dang thue' THEN
        UPDATE vehicles
           SET status = 'Dang thue'
         WHERE vehicle_id = NEW.vehicle_id
           AND status NOT IN ('Bao duong', 'Ngung su dung');
    END IF;

    IF NEW.status IN ('Da tra', 'Da huy') AND OLD.status = 'Dang thue' THEN
        UPDATE vehicles v
           SET v.status = 'San sang'
         WHERE v.vehicle_id = NEW.vehicle_id
           AND v.status = 'Dang thue'
           AND NOT EXISTS (SELECT 1 FROM rentals r
                            WHERE r.vehicle_id = NEW.vehicle_id
                              AND r.status = 'Dang thue');
    END IF;

    IF NEW.return_odometer IS NOT NULL AND NEW.return_odometer > 0 THEN
        UPDATE vehicles
           SET odometer = NEW.return_odometer
         WHERE vehicle_id = NEW.vehicle_id
           AND NEW.return_odometer > odometer;
    END IF;
END$$

/* 6.5. Đồng bộ trạng thái xe sau khi XOÁ hợp đồng */
DROP TRIGGER IF EXISTS trg_rentals_ad$$
CREATE TRIGGER trg_rentals_ad
AFTER DELETE ON rentals
FOR EACH ROW
BEGIN
    IF OLD.status = 'Dang thue' THEN
        UPDATE vehicles v
           SET v.status = 'San sang'
         WHERE v.vehicle_id = OLD.vehicle_id
           AND v.status = 'Dang thue'
           AND NOT EXISTS (SELECT 1 FROM rentals r
                            WHERE r.vehicle_id = OLD.vehicle_id
                              AND r.status = 'Dang thue');
    END IF;
END$$

/* 6.6. Kiểm tra khi THÊM phiếu bảo dưỡng */
DROP TRIGGER IF EXISTS trg_maint_bi$$
CREATE TRIGGER trg_maint_bi
BEFORE INSERT ON maintenance_orders
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);

    IF NEW.status = 'Hoan thanh' AND NEW.completion_date IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu hoan thanh phai co ngay hoan thanh';
    END IF;

    IF NEW.status = 'Dang thuc hien' THEN
        SELECT status INTO v_status FROM vehicles WHERE vehicle_id = NEW.vehicle_id;

        IF v_status IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe khong ton tai';
        END IF;

        IF v_status = 'Dang thue' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe dang duoc thue, khong the bao duong';
        END IF;
    END IF;
END$$

/* 6.7. Đồng bộ trạng thái xe sau khi THÊM phiếu bảo dưỡng */
DROP TRIGGER IF EXISTS trg_maint_ai$$
CREATE TRIGGER trg_maint_ai
AFTER INSERT ON maintenance_orders
FOR EACH ROW
BEGIN
    IF NEW.status = 'Dang thuc hien' THEN
        UPDATE vehicles
           SET status = 'Bao duong'
         WHERE vehicle_id = NEW.vehicle_id
           AND status <> 'Ngung su dung';
    END IF;

    IF NEW.odometer_at_service IS NOT NULL THEN
        UPDATE vehicles
           SET odometer = NEW.odometer_at_service
         WHERE vehicle_id = NEW.vehicle_id
           AND NEW.odometer_at_service > odometer;
    END IF;
END$$

/* 6.8. Kiểm tra khi SỬA phiếu bảo dưỡng */
DROP TRIGGER IF EXISTS trg_maint_bu$$
CREATE TRIGGER trg_maint_bu
BEFORE UPDATE ON maintenance_orders
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);

    IF NEW.status = 'Hoan thanh' AND NEW.completion_date IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Phieu hoan thanh phai co ngay hoan thanh';
    END IF;

    IF NEW.status = 'Dang thuc hien' THEN
        SELECT status INTO v_status FROM vehicles WHERE vehicle_id = NEW.vehicle_id;

        IF v_status = 'Dang thue' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Xe dang duoc thue, khong the bao duong';
        END IF;
    END IF;
END$$

/* 6.9. Đồng bộ trạng thái xe sau khi SỬA phiếu bảo dưỡng */
DROP TRIGGER IF EXISTS trg_maint_au$$
CREATE TRIGGER trg_maint_au
AFTER UPDATE ON maintenance_orders
FOR EACH ROW
BEGIN
    IF NEW.status = 'Dang thuc hien' THEN
        UPDATE vehicles
           SET status = 'Bao duong'
         WHERE vehicle_id = NEW.vehicle_id
           AND status <> 'Ngung su dung';
    END IF;

    IF NEW.status IN ('Hoan thanh', 'Da huy') AND OLD.status <> NEW.status THEN
        UPDATE vehicles v
           SET v.status = CASE
                            WHEN EXISTS (SELECT 1 FROM rentals r
                                          WHERE r.vehicle_id = NEW.vehicle_id
                                            AND r.status = 'Dang thue')
                            THEN 'Dang thue' ELSE 'San sang'
                          END
         WHERE v.vehicle_id = NEW.vehicle_id
           AND v.status = 'Bao duong'
           AND NOT EXISTS (SELECT 1 FROM maintenance_orders o
                            WHERE o.vehicle_id = NEW.vehicle_id
                              AND o.status = 'Dang thuc hien'
                              AND o.order_id <> NEW.order_id);
    END IF;

    IF NEW.odometer_at_service IS NOT NULL THEN
        UPDATE vehicles
           SET odometer = NEW.odometer_at_service
         WHERE vehicle_id = NEW.vehicle_id
           AND NEW.odometer_at_service > odometer;
    END IF;
END$$

/* 6.10. Đồng bộ trạng thái xe sau khi XOÁ phiếu bảo dưỡng */
DROP TRIGGER IF EXISTS trg_maint_ad$$
CREATE TRIGGER trg_maint_ad
AFTER DELETE ON maintenance_orders
FOR EACH ROW
BEGIN
    IF OLD.status = 'Dang thuc hien' THEN
        UPDATE vehicles v
           SET v.status = CASE
                            WHEN EXISTS (SELECT 1 FROM rentals r
                                          WHERE r.vehicle_id = OLD.vehicle_id
                                            AND r.status = 'Dang thue')
                            THEN 'Dang thue' ELSE 'San sang'
                          END
         WHERE v.vehicle_id = OLD.vehicle_id
           AND v.status = 'Bao duong'
           AND NOT EXISTS (SELECT 1 FROM maintenance_orders o
                            WHERE o.vehicle_id = OLD.vehicle_id
                              AND o.status = 'Dang thuc hien');
    END IF;
END$$

/* 6.11. Chặn xoá xe còn hợp đồng / phiếu bảo dưỡng chưa kết thúc */
DROP TRIGGER IF EXISTS trg_vehicles_bd$$
CREATE TRIGGER trg_vehicles_bd
BEFORE DELETE ON vehicles
FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM rentals
                WHERE vehicle_id = OLD.vehicle_id
                  AND status IN ('Dat truoc', 'Dang thue'))
       OR EXISTS (SELECT 1 FROM maintenance_orders
                   WHERE vehicle_id = OLD.vehicle_id
                     AND status IN ('Cho xu ly', 'Dang thuc hien')) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Khong the xoa xe con hop dong/phieu bao duong';
    END IF;
END$$

DELIMITER ;

/* ============================================================================
   7. BÁO CÁO NHANH (chỉ đọc dữ liệu)
   ============================================================================ */

SELECT '===== DANH SÁCH XE =====' AS bao_cao;
SELECT plate_number, brand_name, model_name, status, daily_rate, owner_name
FROM vw_vehicle_details
ORDER BY plate_number;

SELECT '===== HỢP ĐỒNG ĐANG HIỆU LỰC =====' AS bao_cao;
SELECT rental_id, plate_number, renter_name, start_date, end_date,
       rental_days, total_amount, status
FROM vw_active_rentals
ORDER BY start_date;

SELECT '===== CHI PHÍ BẢO DƯỠNG =====' AS bao_cao;
SELECT order_id, plate_number, order_date, service_type, status,
       labor_cost, parts_cost, total_cost
FROM vw_maintenance_cost
ORDER BY order_id;

SELECT '===== TỔNG HỢP THEO XE =====' AS bao_cao;
SELECT plate_number, brand_name, model_name, completed_rentals,
       rental_revenue, maintenance_orders, labor_cost, parts_cost
FROM vw_vehicle_usage
ORDER BY plate_number;

SELECT '===== DOANH THU THEO THÁNG =====' AS bao_cao;
SELECT * FROM vw_monthly_revenue ORDER BY nam, thang;

/* Gợi ý kiểm thử procedure (bỏ comment để chạy thử):
   CALL sp_search_vehicles('Toyota', NULL);
   CALL sp_add_vehicle('51X-246.80', 8, 3, 'Đỏ', 2024, 950000, 5000, NULL, NULL, @new_vehicle);
   SELECT @new_vehicle;
   CALL sp_register_rental(1, 5, CURRENT_DATE, DATE_ADD(CURRENT_DATE, INTERVAL 2 DAY),
                           2000000, 5, 'Thuê thử', @new_rental);
   SELECT @new_rental;
   CALL sp_return_vehicle(@new_rental, 45400, 100000, DATE_ADD(CURRENT_DATE, INTERVAL 2 DAY));
   CALL sp_revenue_by_month(2026);
*/
