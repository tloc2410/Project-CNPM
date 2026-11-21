# Vehicle frontend (customer-only branch)

Branch: `feature/vehicle-figma`.

This branch keeps the existing authentication module and customer vehicle features:
- `GET /`: homepage and featured vehicles
- `GET /cars`: search, filter, sort and pagination, with Figma-based vehicle list layout
- `GET /cars/<car_id>`: vehicle details and view counter
- `GET /login`, `/signup`, `/logout`, `/forgot-password`, `/reset-password/<token>`, `/dashboard`

Admin vehicle-management routes, corresponding templates, and admin-only CRUD service/repository helpers have been removed because another teammate owns the Admin module.

Run from `SourceCode/`:
```powershell
py -m unittest discover -s Test -p "test_vehicle_*.py" -v
py -m pytest Test/test_auth.py -v
py run.py
```

Uses the shared `group12_car_rental` MySQL schema. `Database/sample_data_vehicles.sql` remains available for demo data. No schema or MySQL rows are deleted by this branch.
