-- Bảng Payments phục vụ module Thanh toán và Admin
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

-- Truy vấn cập nhật trạng thái đơn hàng (Admin)
UPDATE orders 
SET status = 'Confirmed', updated_at = CURRENT_TIMESTAMP 
WHERE order_id = 101 AND status = 'New';