# Raw data is generated, never downloaded

`src/generate_data.py` creates all four source tables with seed `20260812`:

- `zones.csv` — synthetic zones and demand weights;
- `cars.csv` — synthetic fleet;
- `car_statuses_hourly.csv` — one state per vehicle and local hour;
- `rides.csv` and `searches_hourly.csv` — synthetic ride and funnel inputs.

The generated CSVs are excluded from Git because the complete hourly status table is large. They are reproducible with `make reproduce` and are **not** records from Делимобиль or any other real operator.
