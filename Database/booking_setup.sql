-- Group12 Car Rental - Rental Cart & Booking sample data
-- Owner: Do Thu Thao (Issue #4)
--
-- IMPORTANT:
--   Use the team's existing database and tables.
--   Run Database/group12_car_rental.sql to create the schema ONLY if the
--   database has never been initialized. Do not run it again on a live DB.
--   This file creates NO database and NO tables; it only inserts sample data.
--   Existing user accounts, cars and orders are not deleted or replaced.
--   Safe to run multiple times because the sample car codes are unique.

USE group12_car_rental;

-- Reuse categories already used by the Vehicle module (Issue #3).
-- If a category is missing, add only the category ROW, not a new table.
INSERT INTO CarTypes (typeName, description)
SELECT 'Sedan', 'Xe sedan 4-5 cho'
WHERE NOT EXISTS (SELECT 1 FROM CarTypes WHERE typeName = 'Sedan');

INSERT INTO CarTypes (typeName, description)
SELECT 'Electric', 'Xe dien'
WHERE NOT EXISTS (SELECT 1 FROM CarTypes WHERE typeName = 'Electric');

INSERT INTO CarTypes (typeName, description)
SELECT 'Van', 'Xe 7 cho va xe cho nhieu hanh khach'
WHERE NOT EXISTS (SELECT 1 FROM CarTypes WHERE typeName = 'Van');

-- Add booking demo cars with NEW AUTO_INCREMENT IDs.
-- Do not force carID=1..5: those IDs may already belong to the Vehicle module.
-- INSERT IGNORE protects against repeated runs on the same unique code.
INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-VIOS-01', 'Toyota Vios (Booking Demo)',
       '/static/images/booking/car_vios.svg',
       'Automatic; Petrol; Tan Son Nhat Airport',
       4, 600000.00, 'available', 120
FROM CarTypes WHERE typeName = 'Sedan' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-CITY-02', 'Honda City (Booking Demo)',
       '/static/images/booking/car_city.svg',
       'Automatic; Petrol; Tan Son Nhat Airport',
       4, 650000.00, 'available', 98
FROM CarTypes WHERE typeName = 'Sedan' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-VF5-03', 'VinFast VF 5 (Booking Demo)',
       '/static/images/booking/car_vf5.svg',
       'Automatic; Electric; District 1 Showroom',
       4, 700000.00, 'available', 145
FROM CarTypes WHERE typeName = 'Electric' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-VF3-04', 'VinFast VF 3 (Booking Demo)',
       '/static/images/booking/car_vf3.svg',
       'Automatic; Electric; District 1 Showroom',
       4, 500000.00, 'available', 110
FROM CarTypes WHERE typeName = 'Electric' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-CARNIVAL-05', 'Kia Carnival (Booking Demo)',
       '/static/images/booking/car_carnival.svg',
       'Automatic; Diesel; Tan Son Nhat Airport',
       7, 1400000.00, 'available', 84
FROM CarTypes WHERE typeName = 'Van' LIMIT 1;

-- Verification: this module uses the SAME team tables Orders and Oderitem.
SELECT carID, code, name, pricePerDay, status
FROM Cars
WHERE code LIKE 'BOOK-%'
ORDER BY carID;
