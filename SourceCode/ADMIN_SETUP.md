# Group12 Admin — Integration Guide

The Admin UI from Chanh's branch has been adapted to the existing Group12 Flask application. It **does not replace** the customer pages or the existing Cart, Booking and Payment flows.

## 1. Update and launch

From your repository working copy:

```powershell
git switch feature/vehicle-figma
git pull origin feature/vehicle-figma
cd SourceCode
py run.py
```

Keep the existing MySQL database and `.env` settings. You do **not** need a second database. Set a unique, long `SECRET_KEY` in `.env`.

## 2. Create an Admin account safely

Sign up through the normal website first, then use **your own** existing email address in MySQL Workbench:

```sql
USE group12_car_rental;
UPDATE Users
SET role = 'ADMIN', isLocked = 0
WHERE email = 'replace-with-your-registered-email@example.com';

SELECT UserID, fullName, email, role, isLocked
FROM Users
WHERE email = 'replace-with-your-registered-email@example.com';
```

Only a trusted team member should receive the ADMIN role. Do not insert a hard-coded default Admin password into SQL or source code. Log out and log in again after changing roles.

## 3. Pages and features

| Page | Route | What it does |
| --- | --- | --- |
| Dashboard | `/admin` | Fleet totals and recorded payments |
| Vehicles | `/admin/vehicles` | Add, edit, delete, change status; manage types |
| Users | `/admin/users` | List real users; lock/unlock in MySQL |
| Orders | `/admin/orders` | See bookings, confirm, move to renting/returned/completed, cancel |
| Payments | `/admin/payments` | Confirm Pending bank/cash collections after verifying actual funds |
| Reports | `/admin/reports` | Recorded Paid transactions and monthly order counts |

All Admin routes require a logged-in user whose current DB role is `ADMIN` and whose account is not locked. State-changing POST requests require CSRF tokens.

Vehicle statuses in the shared database are lowercase: `available`, `rented`, `maintenance`. Booking order statuses are uppercase: `PENDING`, `CONFIRMED`, `RENTING`, `RETURNED`, `COMPLETED`, `CANCELLED`. A cancelled order cannot be reactivated and a paid cancellation requires refund review.

## 4. Payment Demo and verification

Local debug Student Demo uses the existing `DEMO_PAYMENT_MODE=1` configuration to simulate payment. The customer buttons do not move real money.

For non-demo bank transfer or cash payments, the Admin verifies the actual transfer or cash receipt at `/admin/payments`, then marks the Pending record Paid. Do **not** mark payments Paid merely because a customer scanned a QR or shared a screenshot.

The reports show **recorded Paid transactions**, including simulated Paid amounts in Student Demo. They are **not an audited real-cash revenue statement**.

## 5. Tests

From `SourceCode`:

```powershell
py -m pytest Test/test_admin_integration.py -v
py -m pytest Test/test_cart_booking.py Test/test_payment_flow.py -v
```

GitHub Actions also runs Vehicle, Auth, Booking, Payment and Admin integration tests. Automated Admin tests use a transactional SQLite fixture; verify locally against the team's MySQL database before demonstrating live data.
