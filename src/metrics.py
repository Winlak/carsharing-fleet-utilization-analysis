"""Metric definitions shared by marts, analysis and tests."""

from __future__ import annotations

import math


def safe_divide(numerator: float, denominator: float) -> float:
    """Return a ratio or NaN when its denominator is not positive."""
    if denominator <= 0:
        return math.nan
    return numerator / denominator


def utilization_rate(in_ride_minutes: float, available_car_minutes: float) -> float:
    """Share of serviceable time spent in a ride.

    Serviceable time is available plus in-ride time. Maintenance, charging and
    relocation are deliberately excluded: those cars cannot be offered to a
    customer in the modeled hour.
    """
    return safe_divide(in_ride_minutes, in_ride_minutes + available_car_minutes)


def rides_per_active_car(rides: float, available_car_minutes: float, in_ride_minutes: float) -> float:
    """Trips per serviceable car-hour at the selected reporting grain."""
    active_car_hours = (available_car_minutes + in_ride_minutes) / 60
    return safe_divide(rides, active_car_hours)


def search_to_book_conversion(bookings: float, searches: float) -> float:
    """Share of car-search sessions that result in a booking."""
    return safe_divide(bookings, searches)


def lost_demand_proxy(unserved_searches: float, searches: float) -> float:
    """Lower-bound proxy: searches with no available car in the origin zone."""
    return safe_divide(unserved_searches, searches)
