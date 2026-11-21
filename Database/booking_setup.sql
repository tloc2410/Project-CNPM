-- ============================================================================
-- Module: Rental Cart & Booking (Đỗ Thu Thảo)
-- Project: Group 12 Car Rental
-- Note: File SQL riêng bổ sung cho module Cart & Booking.
--       Không sửa đổi Database/group12_car_rental.sql của nhóm.
--       Khớp 100% schema chuẩn: Users, CarTypes, Cars, Orders, Oderitem.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS group12_car_rental;
USE group12_car_rental;

-- Đảm bảo 2 bảng Orders & Oderitem tồn tại đúng khóa ngoại chuẩn của nhóm
CREATE TABLE IF NOT EXISTS Orders (
    oderID INT AUTO_INCREMENT PRIMARY KEY,
    useID INT NOT NULL,
    orderTime DATETIME,
    status VARCHAR(30),
    receivingMethod VARCHAR(30),
    deliveryFee DECIMAL(12,2),
    deposit DECIMAL(12,2),
    totalPrice DECIMAL(12,2),
    paymentMethod VARCHAR(30),
    FOREIGN KEY (useID) REFERENCES Users(UserID)
);

CREATE TABLE IF NOT EXISTS Oderitem (
    OderitemID INT AUTO_INCREMENT PRIMARY KEY,
    OderID INT NOT NULL,
    CarID INT NOT NULL,
    unitPrice DECIMAL(12,2),
    rentalDays INT,
    pickupDate DATE,
    returnDate DATE,
    FOREIGN KEY (OderID) REFERENCES Orders(oderID),
    FOREIGN KEY (CarID) REFERENCES Cars(carID)
);

-- Index hỗ trợ kiểm tra trùng lịch (Overlap Check) nhanh theo CarID + [pickupDate, returnDate]
SET @idx_exists := (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'Oderitem'
      AND index_name = 'idx_oderitem_car_dates'
);
SET @sql_idx := IF(
    @idx_exists = 0,
    'CREATE INDEX idx_oderitem_car_dates ON Oderitem (CarID, pickupDate, returnDate)',
    'SELECT "Index idx_oderitem_car_dates already exists"'
);
PREPARE stmt FROM @sql_idx;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Dữ liệu mẫu loại xe & xe (idempotent, dùng để kiểm thử Giỏ hàng & Đặt xe)
INSERT IGNORE INTO CarTypes (typeId, typeName, description) VALUES
(1, 'Sedan 4 chỗ', 'Xe sedan 4-5 chỗ tiết kiệm nhiên liệu, phù hợp di chuyển nội đô'),
(2, 'Xe điện SUV', 'Xe điện thông minh, vận hành êm ái'),
(3, 'MPV 7 chỗ', 'Xe gia đình rộng rãi cho nhóm và du lịch'),
(4, 'Sedan hạng sang', 'Xe sang trọng phục vụ công tác và sự kiện');

INSERT IGNORE INTO Cars (carID, TypeID, code, name, pictures, description, numberOfSeats, pricePerDay, status, numberOfViews) VALUES
(1, 1, 'CAR-VIOS-01', 'Toyota Vios', '/static/images/booking/car_vios.svg', 'Automatic · Petrol · Tan Son Nhat Airport', 4, 600000.00, 'available', 120),
(2, 1, 'CAR-CITY-02', 'Honda City', '/static/images/booking/car_city.svg', 'Automatic · Petrol · Tan Son Nhat Airport', 4, 650000.00, 'available', 98),
(3, 2, 'CAR-VF5-03', 'VinFast VF 5', '/static/images/booking/car_vf5.svg', 'Automatic · Electric · District 1 Showroom', 4, 700000.00, 'available', 145),
(4, 2, 'CAR-VF3-04', 'VinFast VF 3', '/static/images/booking/car_vf3.svg', 'Automatic · Electric · District 1 Showroom', 4, 500000.00, 'available', 110),
(5, 3, 'CAR-CARNIVAL-05', 'Kia Carnival', '/static/images/booking/car_carnival.svg', 'Automatic · Diesel · Tan Son Nhat Airport', 7, 1400000.00, 'available', 84);
