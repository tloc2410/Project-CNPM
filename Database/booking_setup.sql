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


SELECT carID, code, name, pricePerDay, status
FROM Cars
WHERE code LIKE 'BOOK-%'
ORDER BY carID;
