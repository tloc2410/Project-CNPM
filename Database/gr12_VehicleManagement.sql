CREATE DATABASE IF NOT EXISTS VehicleManagement
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE VehicleManagement;

-- 1. TAO BANG QUAN LY XE

CREATE TABLE Vehicles (
    VehicleID INT AUTO_INCREMENT PRIMARY KEY,
    Brand VARCHAR(50) NOT NULL,
    Model VARCHAR(50) NOT NULL,
    VehicleType VARCHAR(30) NOT NULL,
    ManufactureYear INT,
    LicensePlate VARCHAR(20) NOT NULL UNIQUE,
    Color VARCHAR(30),
    Price DECIMAL(12,2) NOT NULL,
    Status ENUM(
        'Available',
        'In Use',
        'Maintenance'
    ) DEFAULT 'Available',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (Price >= 0),
    CHECK (
        ManufactureYear IS NULL
        OR ManufactureYear BETWEEN 1900 AND 2100
    )
);

-- 2. TAO BANG QUAN LY BAO TRI XE

CREATE TABLE Maintenance (
    MaintenanceID INT AUTO_INCREMENT PRIMARY KEY,
    VehicleID INT NOT NULL,
    MaintenanceDate DATE NOT NULL,
    Description TEXT,
    Cost DECIMAL(12,2) DEFAULT 0,
    Status ENUM(
        'Pending',
        'In Progress',
        'Completed'
    ) DEFAULT 'Pending',

    FOREIGN KEY (VehicleID)
    REFERENCES Vehicles(VehicleID)
    ON DELETE RESTRICT
    ON UPDATE CASCADE,

    CHECK (Cost >= 0)
);

-- 3. THEM DU LIEU MAU

INSERT INTO Vehicles
(Brand, Model, VehicleType, ManufactureYear,
 LicensePlate, Color, Price, Status)
VALUES
('Toyota', 'Camry', 'Sedan', 2023,
 '51A-12345', 'Black', 800000000, 'Available'),

('Honda', 'Civic', 'Sedan', 2022,
 '51B-23456', 'White', 650000000, 'Available'),

('Ford', 'Ranger', 'Pickup', 2024,
 '51C-34567', 'Blue', 900000000, 'In Use'),

('Mazda', 'CX5', 'SUV', 2023,
 '51D-45678', 'Red', 850000000, 'Maintenance'),

('Hyundai', 'Accent', 'Sedan', 2022,
 '51E-56789', 'Silver', 500000000, 'Available');

-- 4. TAO CAC THU TUC LUU TRU

DELIMITER $$

-- 4.1. THU TUC THEM XE MOI

CREATE PROCEDURE sp_AddVehicle(
    IN p_Brand VARCHAR(50),
    IN p_Model VARCHAR(50),
    IN p_Type VARCHAR(30),
    IN p_Year INT,
    IN p_Plate VARCHAR(20),
    IN p_Color VARCHAR(30),
    IN p_Price DECIMAL(12,2)
)
BEGIN
    INSERT INTO Vehicles(
        Brand, Model, VehicleType,
        ManufactureYear, LicensePlate,
        Color, Price
    )
    VALUES(
        p_Brand, p_Model, p_Type,
        p_Year, p_Plate, p_Color, p_Price
    );
END$$

-- 4.2. THU TUC HIEN THI TOAN BO DANH SACH XE

CREATE PROCEDURE sp_GetAllVehicles()
BEGIN
    SELECT *
    FROM Vehicles
    ORDER BY VehicleID;
END$$

-- 4.3. THU TUC TIM KIEM XE

CREATE PROCEDURE sp_SearchVehicle(
    IN p_Keyword VARCHAR(100)
)
BEGIN
    SELECT *
    FROM Vehicles
    WHERE Brand LIKE CONCAT('%',p_Keyword,'%')
       OR Model LIKE CONCAT('%',p_Keyword,'%')
       OR LicensePlate LIKE CONCAT('%',p_Keyword,'%');
END$$

-- 4.4. THU TUC CAP NHAT THONG TIN XE

CREATE PROCEDURE sp_UpdateVehicle(
    IN p_ID INT,
    IN p_Brand VARCHAR(50),
    IN p_Model VARCHAR(50),
    IN p_Type VARCHAR(30),
    IN p_Year INT,
    IN p_Color VARCHAR(30),
    IN p_Price DECIMAL(12,2)
)
BEGIN
    UPDATE Vehicles
    SET Brand = p_Brand,
        Model = p_Model,
        VehicleType = p_Type,
        ManufactureYear = p_Year,
        Color = p_Color,
        Price = p_Price
    WHERE VehicleID = p_ID;
END$$

-- 4.5. THU TUC XOA XE

CREATE PROCEDURE sp_DeleteVehicle(
    IN p_ID INT
)
BEGIN
    DELETE FROM Vehicles
    WHERE VehicleID = p_ID;
END$$

-- 4.6. THU TUC CAP NHAT TRANG THAI XE

CREATE PROCEDURE sp_UpdateVehicleStatus(
    IN p_ID INT,
    IN p_Status VARCHAR(20)
)
BEGIN
    IF p_Status NOT IN (
        'Available',
        'In Use',
        'Maintenance'
    ) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Invalid vehicle status';
    END IF;

    UPDATE Vehicles
    SET Status = p_Status
    WHERE VehicleID = p_ID;
END$$

-- 4.7. THU TUC THEM THONG TIN BAO TRI XE

CREATE PROCEDURE sp_AddMaintenance(
    IN p_VehicleID INT,
    IN p_Date DATE,
    IN p_Description TEXT,
    IN p_Cost DECIMAL(12,2)
)
BEGIN
    DECLARE v_Status VARCHAR(20);

    SELECT Status INTO v_Status
    FROM Vehicles
    WHERE VehicleID = p_VehicleID;

    IF v_Status = 'In Use' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Vehicle is currently in use';
    END IF;

    INSERT INTO Maintenance(
        VehicleID,
        MaintenanceDate,
        Description,
        Cost
    )
    VALUES(
        p_VehicleID,
        p_Date,
        p_Description,
        p_Cost
    );

    UPDATE Vehicles
    SET Status = 'Maintenance'
    WHERE VehicleID = p_VehicleID;
END$$

DELIMITER ;

-- 5. TAO TRIGGER

DELIMITER $$

-- TU DONG CAP NHAT TRANG THAI XE
-- KHI CONG VIEC BAO TRI DA HOAN THANH

CREATE TRIGGER trg_MaintenanceCompleted
AFTER UPDATE ON Maintenance
FOR EACH ROW
BEGIN
    IF NEW.Status = 'Completed'
       AND OLD.Status <> 'Completed' THEN

        IF NOT EXISTS (
            SELECT 1
            FROM Maintenance
            WHERE VehicleID = NEW.VehicleID
            AND Status <> 'Completed'
        ) THEN
            UPDATE Vehicles
            SET Status = 'Available'
            WHERE VehicleID = NEW.VehicleID
            AND Status = 'Maintenance';
        END IF;

    END IF;
END$$

DELIMITER ;

-- 6. TAO CAC VIEW

-- VIEW HIEN THI THONG TIN DANH SACH XE

CREATE OR REPLACE VIEW vw_VehicleList AS
SELECT
    VehicleID,
    Brand,
    Model,
    VehicleType,
    ManufactureYear,
    LicensePlate,
    Color,
    Price,
    Status
FROM Vehicles;

-- VIEW HIEN THI THONG TIN BAO TRI XE

CREATE OR REPLACE VIEW vw_MaintenanceList AS
SELECT
    m.MaintenanceID,
    v.Brand,
    v.Model,
    v.LicensePlate,
    m.MaintenanceDate,
    m.Description,
    m.Cost,
    m.Status
FROM Maintenance m
JOIN Vehicles v
ON m.VehicleID = v.VehicleID;

-- 7. CAC CAU LENH THONG KE VA BAO CAO

-- 7.1. THONG KE TONG SO LUONG XE

SELECT COUNT(*) AS TotalVehicles
FROM Vehicles;

-- 7.2. THONG KE SO LUONG XE THEO TRANG THAI

SELECT Status, COUNT(*) AS Total
FROM Vehicles
GROUP BY Status;

-- 7.3. THONG KE SO LUONG XE THEO LOAI XE

SELECT VehicleType, COUNT(*) AS Total
FROM Vehicles
GROUP BY VehicleType;

-- 7.4. TINH TONG GIA TRI CAC XE

SELECT SUM(Price) AS TotalVehicleValue
FROM Vehicles;

-- 7.5. TINH TONG CHI PHI BAO TRI XE

SELECT SUM(Cost) AS TotalMaintenanceCost
FROM Maintenance;
