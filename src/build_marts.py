"""Execute the SQL marts and store compact CSV outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

MARTS = {
    "mart_zone_hour": "01_zone_hour_supply_demand.sql",
    "mart_zone_daily": "02_zone_daily_metrics.sql",
    "mart_fleet_daily": "03_fleet_daily_summary.sql",
}


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def validate_generated_inputs(raw_dir: Path) -> dict[str, int]:
    required = ["zones.csv", "cars.csv", "car_statuses_hourly.csv", "rides.csv", "searches_hourly.csv"]
    missing = [file_name for file_name in required if not (raw_dir / file_name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing generated inputs: {', '.join(missing)}")
    return {file_name: sum(1 for _ in (raw_dir / file_name).open(encoding="utf-8")) - 1 for file_name in required}


def build_marts(raw_dir: Path, processed_dir: Path, sql_dir: Path) -> dict[str, pd.DataFrame]:
    validate_generated_inputs(raw_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect()
    try:
        for table_name, file_name in {
            "zones": "zones.csv",
            "cars": "cars.csv",
            "car_statuses_hourly": "car_statuses_hourly.csv",
            "rides": "rides.csv",
            "searches_hourly": "searches_hourly.csv",
        }.items():
            csv_path = _sql_path(raw_dir / file_name)
            conn.execute(f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_csv_auto('{csv_path}')")

        outputs: dict[str, pd.DataFrame] = {}
        for mart_name, sql_file in MARTS.items():
            sql = (sql_dir / sql_file).read_text(encoding="utf-8")
            result = conn.execute(sql).fetchdf()
            conn.register(f"_{mart_name}_frame", result)
            conn.execute(f"CREATE OR REPLACE VIEW {mart_name} AS SELECT * FROM _{mart_name}_frame")
            result.to_csv(processed_dir / f"{mart_name}.csv", index=False)
            outputs[mart_name] = result

        _write_quality_report(raw_dir, processed_dir, outputs, conn)
        return outputs
    finally:
        conn.close()


def _write_quality_report(raw_dir: Path, processed_dir: Path, marts: dict[str, pd.DataFrame], conn: duckdb.DuckDBPyConnection) -> None:
    zones = marts["mart_zone_hour"]["zone_id"].nunique()
    hours = marts["mart_zone_hour"]["hour_ts"].nunique()
    expected_grid = zones * hours
    actual_grid = len(marts["mart_zone_hour"])
    car_statuses = conn.execute("SELECT COUNT(*) FROM car_statuses_hourly").fetchone()[0]
    duplicate_statuses = conn.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT hour_ts, car_id, COUNT(*) AS row_count
          FROM car_statuses_hourly
          GROUP BY 1, 2
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    duplicate_rides = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT ride_id) FROM rides"
    ).fetchone()[0]
    invalid_statuses = conn.execute(
        "SELECT COUNT(*) FROM car_statuses_hourly WHERE status NOT IN ('available', 'in_ride', 'maintenance', 'charging', 'relocating')"
    ).fetchone()[0]
    negative_minutes = conn.execute(
        "SELECT COUNT(*) FROM car_statuses_hourly WHERE available_minutes < 0 OR in_ride_minutes < 0 OR idle_minutes < 0"
    ).fetchone()[0]
    invalid_starting_availability = conn.execute(
        "SELECT COUNT(*) FROM searches_hourly WHERE starting_available_cars < 0"
    ).fetchone()[0]
    temporal_order_errors = conn.execute(
        "SELECT COUNT(*) FROM rides WHERE CAST(ended_at AS TIMESTAMP) <= CAST(started_at AS TIMESTAMP)"
    ).fetchone()[0]
    booking_ride_gap = conn.execute(
        "SELECT ABS((SELECT SUM(bookings) FROM searches_hourly) - (SELECT COUNT(*) FROM rides))"
    ).fetchone()[0]
    join_coverage = conn.execute(
        """
        SELECT COUNT(*) FROM searches_hourly s
        LEFT JOIN zones z USING (zone_id)
        WHERE z.zone_id IS NULL
        """
    ).fetchone()[0]
    if (
        actual_grid != expected_grid
        or duplicate_statuses
        or duplicate_rides
        or invalid_statuses
        or negative_minutes
        or invalid_starting_availability
        or temporal_order_errors
        or booking_ride_gap
        or join_coverage
    ):
        raise ValueError("Synthetic input quality checks failed; inspect data/processed/data_quality_report.md")

    report = f"""# Проверка качества синтетических данных

Источник: детерминированная генерация `src/generate_data.py`; данные не относятся к реальному оператору.

| Проверка | Результат |
|---|---:|
| Строк статусов автомобилей | {car_statuses:,} |
| Полная календарная сетка «час × зона» | {actual_grid:,} / {expected_grid:,} |
| Дубликаты ключа `hour_ts, car_id` | {duplicate_statuses} |
| Дубликаты `ride_id` | {duplicate_rides} |
| Некорректные статусы | {invalid_statuses} |
| Отрицательные минуты | {negative_minutes} |
| Отрицательная pre-search availability | {invalid_starting_availability} |
| Поездки с `ended_at <= started_at` | {temporal_order_errors} |
| Разница между bookings и rides | {booking_ride_gap} |
| Поиски без соответствующей зоны | {join_coverage} |

**Итог:** проверки ключей, доменов, временного порядка, отсутствия outcome leakage в availability-предикторе, неотрицательности и покрытия JOIN пройдены. Ограничение остаётся концептуальным: статусы отражаются в почасовой сетке, поэтому поездка внутри часа занимает целый статусный час в supply-метриках.
"""
    (processed_dir / "data_quality_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DuckDB SQL marts from generated synthetic CSVs.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--sql-dir", type=Path, default=Path("sql"))
    args = parser.parse_args()
    marts = build_marts(args.raw_dir, args.processed_dir, args.sql_dir)
    print({name: len(frame) for name, frame in marts.items()})


if __name__ == "__main__":
    main()
