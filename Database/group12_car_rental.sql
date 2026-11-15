CREATE DATABASE IF NOT EXISTS group12_car_rental;
USE group12_car_rental;

CREATE TABLE Users (
    UserID INT AUTO_INCREMENT PRIMARY KEY,
    fullName VARCHAR(100) NOT NULL,
    dateOfBirth DATE,
    gender VARCHAR(20),
    address VARCHAR(255),
    phone VARCHAR(20),
    email VARCHAR(100) NOT NULL UNIQUE,
    passwordHash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'CUSTOMER',
    isLocked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE CarTypes (
    typeId INT AUTO_INCREMENT PRIMARY KEY,
    typeName VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE Cars (
    carID INT AUTO_INCREMENT PRIMARY KEY,
    TypeID INT NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    pictures TEXT,
    description TEXT,
    numberOfSeats INT,
    pricePerDay DECIMAL(12,2) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'available',
    numberOfViews INT NOT NULL DEFAULT 0,
    FOREIGN KEY (TypeID) REFERENCES CarTypes(typeId)
);

CREATE TABLE Orders (
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

CREATE TABLE Oderitem (
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

CREATE TABLE Payments (
    paymentID INT AUTO_INCREMENT PRIMARY KEY,
    oderID INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    paymentMethod VARCHAR(30),
    paymentStatus VARCHAR(30),
    transactionCode VARCHAR(100),
    paidAt DATETIME,
    FOREIGN KEY (oderID) REFERENCES Orders(oderID)
);
