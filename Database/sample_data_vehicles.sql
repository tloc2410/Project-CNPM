USE group12_car_rental;

INSERT IGNORE INTO CarTypes (typeId, typeName, description) VALUES
    (1, 'Sedan', 'Xe sedan 4-5 cho, phu hop di lai thanh pho va di cong tac.'),
    (2, 'SUV', 'Xe SUV gan cao, khoang lang rong, phu hop di du lich.'),
    (3, 'Hatchback', 'Xe nho gon, tiet kien nhien lieu, phu hop 2-4 nguoi.'),
    (4, 'Luxury', 'Xe cao cap cho cac su kien va dich vu khach hang dac biet.'),
    (5, 'Van', 'Xe 16 cho, phu hop doan khach va cho hang nho.'),
    (6, 'Electric', 'Xe dien, khong phat thai, chi phi van hanh thap.');

INSERT IGNORE INTO Cars
    (carID, TypeID, code, name, pictures, description, numberOfSeats, pricePerDay, status, numberOfViews)
VALUES
    (1,  1, 'SEDAN-01', 'Toyota Vios 2023',   'toyotavios2023.webp',       'May 1.5L, hop so tu dong, dieu hoa, camera lui xe.',        5,  850000.00, 'available',   42),
    (2,  1, 'SEDAN-02', 'Honda City 2022',    'hondacity2022.webp',        'Noi that sang, tieu hao nhien lieu thap, phu hop gia dinh.', 5,  900000.00, 'rented',      31),
    (3,  2, 'SUV-01',   'Toyota Corolla Cross','toyotacorollacross.webp',  'SUV 5 cho, giam sat hanh trinh, camera 360.',               5, 1250000.00, 'available',   78),
    (4,  2, 'SUV-02',   'Mazda CX-5 2023',    'mazdacx-52023.webp',        'Dong co 2.0L, he thong am thanh Bose, ghe da.',            5, 1400000.00, 'available',   65),
    (5,  3, 'HATCH-01', 'Kia Morning 2022',   'kiamorning2022.webp',       'Xe nho gon, de dau xe, phu hop di lai noi thanh.',          4,  650000.00, 'available',   24),
    (6,  3, 'HATCH-02', 'Hyundai i10 2023',   'hyundaii102023.webp',       'May 1.2L, tiet kien nhien lieu, bao hanh chinh hang.',      4,  680000.00, 'maintenance', 12),
    (7,  4, 'LUX-01',   'Mercedes C200 2022','marcedesc200202022.webp',   'Xe cao cap, noi that da, trang bi day du cho su kien.',      5, 3200000.00, 'available',  156),
    (8,  4, 'LUX-02',   'BMW 320i 2023',     'bmw320i2023.webp',           'Dong co turbo, lai the thao, giao dich dang cap.',          5, 3500000.00, 'rented',     133),
    (9,  5, 'VAN-01',   'Toyota Hiace 2021', 'toyotahiace2021.webp',       'Xe 16 cho, phu hop doan khach, co khoang hanh ly va thang xe.',    16, 1800000.00, 'available',   57),
    (10, 6, 'ELEC-01',  'VinFast VF e34',    'vinfastVFe34.webp',          'Xe dien, pin day du, sac nhanh, khong phat thai.',          5, 1100000.00, 'available',   94),
    (11, 6, 'ELEC-02',  'Tesla Model 3',     'teslamodel3.webp',           'Xe dien, vanh xe tu dong, noi that toi gian.',              5, 2600000.00, 'maintenance', 88),
    (12, 2, 'SUV-03',   'Honda CR-V 2021',   'hondacrV2021.webp',          'SUV 7 cho, 7 airbag, phu hop gia dinh lon.',                7, 1500000.00, 'available',   71);

-- Kiem tra nhanh sau khi chay:
-- SELECT c.carID, c.code, c.name, t.typeName, c.pricePerDay, c.status
-- FROM Cars c LEFT JOIN CarTypes t ON t.typeId = c.TypeID
-- ORDER BY c.carID;

-- Cap nhat anh cho database da co san (INSERT IGNORE khong ghi de du cu).
UPDATE Cars SET pictures = 'toyotavios2023.webp'     WHERE carID = 1;
UPDATE Cars SET pictures = 'hondacity2022.webp'      WHERE carID = 2;
UPDATE Cars SET pictures = 'toyotacorollacross.webp' WHERE carID = 3;
UPDATE Cars SET pictures = 'mazdacx-52023.webp'      WHERE carID = 4;
UPDATE Cars SET pictures = 'kiamorning2022.webp'     WHERE carID = 5;
UPDATE Cars SET pictures = 'hyundaii102023.webp'     WHERE carID = 6;
UPDATE Cars SET pictures = 'marcedesc200202022.webp' WHERE carID = 7;
UPDATE Cars SET pictures = 'bmw320i2023.webp'        WHERE carID = 8;
UPDATE Cars SET pictures = 'toyotahiace2021.webp'    WHERE carID = 9;
UPDATE Cars SET pictures = 'vinfastVFe34.webp'       WHERE carID = 10;
UPDATE Cars SET pictures = 'teslamodel3.webp'        WHERE carID = 11;
UPDATE Cars SET pictures = 'hondacrV2021.webp'       WHERE carID = 12;
