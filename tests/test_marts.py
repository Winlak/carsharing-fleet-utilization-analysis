from datetime import datetime

from src.build_marts import build_marts
from src.generate_data import run_generator


def test_calendar_grid_and_metric_bounds(tmp_path) -> None:
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    sql_dir = __import__("pathlib").Path(__file__).resolve().parents[1] / "sql"
    run_generator(raw, datetime(2025, 1, 1), hours=48, car_count=24, seed=7)
    marts = build_marts(raw, processed, sql_dir)
    zone_hour = marts["mart_zone_hour"]
    assert len(zone_hour) == 48 * 12
    assert zone_hour[["available_car_minutes", "in_ride_minutes", "searches"]].ge(0).all().all()
    bounded_rates = zone_hour.dropna(subset=["search_to_book_conversion", "lost_demand_proxy"])
    assert bounded_rates["search_to_book_conversion"].between(0, 1).all()
    assert bounded_rates["lost_demand_proxy"].between(0, 1).all()
