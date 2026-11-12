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
