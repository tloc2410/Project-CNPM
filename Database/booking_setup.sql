USE group12_car_rental;

INSERT INTO CarTypes (typeName, description)
SELECT 'Sedan', 'Xe sedan 4-5 cho'
WHERE NOT EXISTS (SELECT 1 FROM CarTypes WHERE typeName = 'Sedan');

INSERT INTO CarTypes (typeName, description)
SELECT 'Electric', 'Xe dien'
WHERE NOT EXISTS (SELECT 1 FROM CarTypes WHERE typeName = 'Electric');

INSERT INTO CarTypes (typeName, description)
SELECT 'Van', 'Xe 7 cho va xe cho nhieu hanh khach'
WHERE NOT EXISTS (SELECT 1 FROM CarTypes WHERE typeName = 'Van');

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-VIOS-01', 'Toyota Vios',
       'toyotavios2023.webp',
       'Automatic; Petrol; Tan Son Nhat Airport',
       4, 600000.00, 'available', 120
FROM CarTypes WHERE typeName = 'Sedan' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-CITY-02', 'Honda City',
       'hondacity2022.webp',
       'Automatic; Petrol; Tan Son Nhat Airport',
       4, 650000.00, 'available', 98
FROM CarTypes WHERE typeName = 'Sedan' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-VF5-03', 'VinFast VF 5',
       'https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960',
       'Automatic; Electric; District 1 Showroom',
       4, 700000.00, 'available', 145
FROM CarTypes WHERE typeName = 'Electric' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-VF3-04', 'VinFast VF 3',
       '/static/images/cars/vinfast_vf3.jpg',
       'Automatic; Electric; District 1 Showroom',
       4, 500000.00, 'available', 110
FROM CarTypes WHERE typeName = 'Electric' LIMIT 1;

INSERT IGNORE INTO Cars
    (TypeID, code, name, pictures, description,
     numberOfSeats, pricePerDay, status, numberOfViews)
SELECT typeId, 'BOOK-CARNIVAL-05', 'Kia Carnival',
       '/static/images/cars/kia_carnival.jpg',
       'Automatic; Diesel; Tan Son Nhat Airport',
       7, 1400000.00, 'available', 84
FROM CarTypes WHERE typeName = 'Van' LIMIT 1;


SELECT carID, code, name, pricePerDay, status
FROM Cars
WHERE code LIKE 'BOOK-%'
ORDER BY carID;

-- Fix the picture field of the three existing booking demo cars by unique code.
-- Safe on the existing group database; orders and other vehicles are unaffected.
UPDATE Cars SET pictures = 'toyotavios2023.webp' WHERE code = 'BOOK-VIOS-01';
UPDATE Cars SET pictures = 'hondacity2022.webp' WHERE code = 'BOOK-CITY-02';
UPDATE Cars SET pictures = 'https://commons.wikimedia.org/wiki/Special:FilePath/VinFast_VF5.jpg?width=960' WHERE code = 'BOOK-VF5-03';
