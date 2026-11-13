create database group12_car_rental;

use group12_car_rental;


CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20),
    address VARCHAR(255),
    phone VARCHAR(20),
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_locked BOOLEAN DEFAULT FALSE,
    role ENUM('CUSTOMER', 'ADMIN') DEFAULT 'CUSTOMER'
);
CREATE TABLE Orders (
    oderID INT PRIMARY KEY AUTO_INCREMENT,
    useID INT,
    orderTime DATETIME,
    status VARCHAR(30),
    receivingMethod VARCHAR(30),
    deliveryFee DECIMAL(12, 2),
    deposit DECIMAL(12, 2),
    totalPrice DECIMAL(12, 2),
    paymentMethod VARCHAR(30)
);

CREATE TABLE Oderitem (
    OderitemID INT PRIMARY KEY AUTO_INCREMENT,
    OderID INT,
    CarID INT,
    unitPrice DECIMAL(12, 2),
    rentalDays INT,
    pickupDate DATE,
    returnDate DATE,
    FOREIGN KEY (OderID) REFERENCES Orders(oderID)
);

CREATE TABLE Car (
    carID INT PRIMARY KEY AUTO_INCREMENT,
    TypeID INT,
    code VARCHAR(50),
    name VARCHAR(150),
    pictures TEXT,
    description TEXT,
    numberOfSeats INT,
    pricePerDay DECIMAL(12,2),
    status VARCHAR(30),
    numberOfViews INT,
    FOREIGN KEY (TypeID) REFERENCES CarTypes(typeID)
);

CREATE TABLE CarTypes (
    typeID INT PRIMARY KEY AUTO_INCREMENT,
    typeName VARCHAR(100),
    description TEXT
);

- Bảng Payments phục vụ module Thanh toán và Admin
CREATE TABLE IF NOT EXISTS payments (
    payment_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL, 
    payment_method VARCHAR(50) NOT NULL CHECK (payment_method IN ('CASH', 'ONLINE_SIMULATED')),
    amount DECIMAL(12, 2) NOT NULL CHECK (amount >= 0),
    transaction_ref VARCHAR(100) UNIQUE, 
    payment_status VARCHAR(30) NOT NULL DEFAULT 'PENDING' 
        CHECK (payment_status IN ('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED')),
    paid_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

