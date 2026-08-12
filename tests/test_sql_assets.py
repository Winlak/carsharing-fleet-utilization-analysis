from pathlib import Path


def test_sql_demonstrates_real_modeling_patterns() -> None:
    root = Path(__file__).resolve().parents[1] / "sql"
    hourly_sql = (root / "01_zone_hour_supply_demand.sql").read_text(encoding="utf-8").upper()
    daily_sql = (root / "02_ZONE_DAILY_METRICS.SQL".lower()).read_text(encoding="utf-8").upper()
    assert "WITH" in hourly_sql
    assert "CROSS JOIN" in hourly_sql
    assert "LEFT JOIN" in hourly_sql
    assert "LAG(" in hourly_sql
    assert "ROWS BETWEEN 167 PRECEDING" in hourly_sql
    assert "RANK() OVER" in daily_sql
