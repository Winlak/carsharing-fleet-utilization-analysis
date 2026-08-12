import math

from src.metrics import (
    lost_demand_proxy,
    rides_per_active_car,
    safe_divide,
    search_to_book_conversion,
    utilization_rate,
)


def test_utilization_uses_serviceable_minutes_only() -> None:
    assert utilization_rate(30, 90) == 0.25


def test_rides_per_active_car_uses_car_hours() -> None:
    assert rides_per_active_car(3, 60, 60) == 1.5


def test_funnel_rates_and_zero_denominators() -> None:
    assert search_to_book_conversion(18, 30) == 0.6
    assert lost_demand_proxy(3, 30) == 0.1
    assert math.isnan(safe_divide(1, 0))
