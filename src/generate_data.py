"""Generate deterministic, clearly labelled synthetic carsharing data.

The generator models hourly supply, search sessions and booked rides. It is a
portfolio exercise only; no records, parameters or conclusions represent a
real carsharing operator.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ZONE_ROWS = [
    ("Z01", "Центр", "central", 1.45, 55.751, 37.618),
    ("Z02", "Деловой квартал", "business", 1.65, 55.742, 37.549),
    ("Z03", "Вокзальный узел", "transit", 1.35, 55.776, 37.655),
    ("Z04", "Университетский", "education", 1.10, 55.700, 37.530),
    ("Z05", "Технопарк", "business", 1.25, 55.685, 37.664),
    ("Z06", "Северный жилой", "residential", 0.95, 55.842, 37.568),
    ("Z07", "Восточный жилой", "residential", 0.90, 55.762, 37.780),
    ("Z08", "Южный жилой", "residential", 1.00, 55.632, 37.654),
    ("Z09", "Западный жилой", "residential", 0.85, 55.732, 37.420),
    ("Z10", "Набережная", "leisure", 1.15, 55.730, 37.610),
    ("Z11", "Аэропорт", "airport", 0.75, 55.972, 37.414),
    ("Z12", "Парк и события", "leisure", 0.80, 55.728, 37.502),
]

STATUS_FIELDS = [
    "hour_ts",
    "car_id",
    "zone_id",
    "status",
    "available_minutes",
    "in_ride_minutes",
    "idle_minutes",
]


def hour_factor(hour: int) -> float:
    if 0 <= hour <= 4:
        return 0.18
    if 5 <= hour <= 6:
        return 0.55
    if 7 <= hour <= 10:
        return 1.70
    if 11 <= hour <= 16:
        return 1.10
    if 17 <= hour <= 21:
        return 1.90
    return 0.62


def seasonal_factor(timestamp: datetime) -> float:
    """Deliberate annual seasonality: higher activity in warmer months."""
    day_of_year = timestamp.timetuple().tm_yday
    return 0.88 + 0.24 * (1 + math.sin(2 * math.pi * (day_of_year - 112) / 365)) / 2


def zone_demand_factor(zone_type: str, timestamp: datetime) -> float:
    weekend = timestamp.weekday() >= 5
    hour = timestamp.hour
    if zone_type == "business":
        return 0.65 if weekend else (1.55 if 8 <= hour <= 19 else 0.75)
    if zone_type == "residential":
        return 1.15 if weekend else (1.30 if hour in {7, 8, 18, 19, 20} else 0.95)
    if zone_type == "leisure":
        return 1.50 if weekend and 11 <= hour <= 22 else 0.85
    if zone_type == "airport":
        return 1.00 + (0.30 if hour in {5, 6, 7, 20, 21, 22} else 0)
    return 1.00


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def timestamp_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def choose_destination(rng: np.random.Generator, origin_zone: str, zone_ids: list[str]) -> str:
    """Favor central/transit destinations without making any route deterministic."""
    weights = np.array([1.0] * len(zone_ids), dtype=float)
    weights[zone_ids.index(origin_zone)] = 0.18
    for preferred in ("Z01", "Z02", "Z03", "Z10"):
        if preferred != origin_zone:
            weights[zone_ids.index(preferred)] *= 1.55
    return str(rng.choice(zone_ids, p=weights / weights.sum()))


def write_static_dimensions(output_dir: Path, rng: np.random.Generator, car_count: int) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "zones.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["zone_id", "zone_name", "zone_type", "demand_weight", "latitude", "longitude"])
        writer.writeheader()
        for zone_id, zone_name, zone_type, demand_weight, latitude, longitude in ZONE_ROWS:
            writer.writerow(
                {
                    "zone_id": zone_id,
                    "zone_name": zone_name,
                    "zone_type": zone_type,
                    "demand_weight": demand_weight,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

    zone_ids = [row[0] for row in ZONE_ROWS]
    cars: list[dict[str, object]] = []
    with (output_dir / "cars.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["car_id", "model_group", "initial_zone_id", "battery_pct"])
        writer.writeheader()
        for car_number in range(1, car_count + 1):
            initial_zone = str(rng.choice(zone_ids, p=np.array([row[3] for row in ZONE_ROWS]) / sum(row[3] for row in ZONE_ROWS)))
            car = {
                "car_id": f"CAR-{car_number:03d}",
                "model_group": "compact" if car_number % 4 else "comfort",
                "initial_zone_id": initial_zone,
                "battery_pct": int(rng.integers(48, 96)),
                "zone_id": initial_zone,
                "busy_until": None,
                "destination_zone": None,
                "maintenance_until": None,
                "charging_until": None,
                "relocating_until": None,
                "relocation_destination": None,
            }
            cars.append(car)
            writer.writerow({key: car[key] for key in ["car_id", "model_group", "initial_zone_id", "battery_pct"]})
    return cars


def release_completed_state(car: dict[str, object], current_hour: datetime) -> None:
    if car["busy_until"] is not None and car["busy_until"] <= current_hour:
        car["zone_id"] = car["destination_zone"]
        car["busy_until"] = None
        car["destination_zone"] = None
    if car["relocating_until"] is not None and car["relocating_until"] <= current_hour:
        car["zone_id"] = car["relocation_destination"]
        car["relocating_until"] = None
        car["relocation_destination"] = None
    if car["maintenance_until"] is not None and car["maintenance_until"] <= current_hour:
        car["maintenance_until"] = None
    if car["charging_until"] is not None and car["charging_until"] <= current_hour:
        car["charging_until"] = None


def current_status(car: dict[str, object], current_hour: datetime) -> str:
    if car["busy_until"] is not None and car["busy_until"] > current_hour:
        return "in_ride"
    if car["maintenance_until"] is not None and car["maintenance_until"] > current_hour:
        return "maintenance"
    if car["charging_until"] is not None and car["charging_until"] > current_hour:
        return "charging"
    if car["relocating_until"] is not None and car["relocating_until"] > current_hour:
        return "relocating"
    return "available"


def run_generator(output_dir: Path, start: datetime, hours: int, car_count: int, seed: int) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    cars = write_static_dimensions(output_dir, rng, car_count)
    zone_lookup = {row[0]: {"name": row[1], "type": row[2], "weight": row[3]} for row in ZONE_ROWS}
    zone_ids = list(zone_lookup)

    status_path = output_dir / "car_statuses_hourly.csv"
    rides_path = output_dir / "rides.csv"
    searches_path = output_dir / "searches_hourly.csv"
    generated_rides = 0
    generated_searches = 0
    generated_unserved = 0

    with status_path.open("w", newline="", encoding="utf-8") as status_file, rides_path.open("w", newline="", encoding="utf-8") as rides_file, searches_path.open("w", newline="", encoding="utf-8") as searches_file:
        status_writer = csv.DictWriter(status_file, fieldnames=STATUS_FIELDS)
        ride_writer = csv.DictWriter(
            rides_file,
            fieldnames=["ride_id", "car_id", "started_at", "ended_at", "origin_zone_id", "destination_zone_id", "duration_minutes"],
        )
        search_writer = csv.DictWriter(
            searches_file,
            fieldnames=[
                "hour_ts",
                "zone_id",
                "starting_available_cars",
                "searches",
                "bookings",
                "unserved_searches",
                "abandoned_searches",
            ],
        )
        status_writer.writeheader()
        ride_writer.writeheader()
        search_writer.writeheader()

        for hour_index in range(hours):
            current_hour = start + timedelta(hours=hour_index)
            for car in cars:
                release_completed_state(car, current_hour)

            # Small offline share keeps serviceable denominator explicit.
            for car in cars:
                if current_status(car, current_hour) != "available":
                    continue
                draw = rng.random()
                if draw < 0.00022:
                    car["maintenance_until"] = current_hour + timedelta(hours=int(rng.integers(3, 8)))
                elif draw < 0.00082:
                    car["charging_until"] = current_hour + timedelta(hours=int(rng.integers(1, 3)))
                elif draw < 0.00108:
                    car["relocating_until"] = current_hour + timedelta(hours=1)
                    car["relocation_destination"] = choose_destination(rng, str(car["zone_id"]), zone_ids)

            available_by_zone: dict[str, list[dict[str, object]]] = {zone_id: [] for zone_id in zone_ids}
            for car in cars:
                if current_status(car, current_hour) == "available":
                    available_by_zone[str(car["zone_id"])].append(car)

            for zone_id in zone_ids:
                zone = zone_lookup[zone_id]
                starting_available_cars = len(available_by_zone[zone_id])
                demand_lambda = 2.35 * float(zone["weight"]) * hour_factor(current_hour.hour) * seasonal_factor(current_hour)
                demand_lambda *= zone_demand_factor(str(zone["type"]), current_hour)
                searches = int(rng.poisson(max(demand_lambda, 0.05)))
                bookings = 0
                unserved = 0
                abandoned = 0
                for _ in range(searches):
                    pool = available_by_zone[zone_id]
                    if not pool:
                        unserved += 1
                        continue
                    booking_probability = sigmoid(-0.82 + 0.19 * len(pool))
                    if rng.random() >= booking_probability:
                        abandoned += 1
                        continue
                    car = pool.pop(int(rng.integers(0, len(pool))))
                    start_minute = int(rng.integers(0, 60))
                    duration_minutes = int(np.clip(rng.gamma(shape=2.4, scale=17.0) + 10, 12, 110))
                    ride_start = current_hour + timedelta(minutes=start_minute)
                    ride_end = ride_start + timedelta(minutes=duration_minutes)
                    destination = choose_destination(rng, zone_id, zone_ids)
                    car["busy_until"] = ride_end
                    car["destination_zone"] = destination
                    generated_rides += 1
                    bookings += 1
                    ride_writer.writerow(
                        {
                            "ride_id": f"RIDE-{generated_rides:07d}",
                            "car_id": car["car_id"],
                            "started_at": timestamp_text(ride_start),
                            "ended_at": timestamp_text(ride_end),
                            "origin_zone_id": zone_id,
                            "destination_zone_id": destination,
                            "duration_minutes": duration_minutes,
                        }
                    )
                generated_searches += searches
                generated_unserved += unserved
                search_writer.writerow(
                    {
                        "hour_ts": timestamp_text(current_hour),
                        "zone_id": zone_id,
                        "starting_available_cars": starting_available_cars,
                        "searches": searches,
                        "bookings": bookings,
                        "unserved_searches": unserved,
                        "abandoned_searches": abandoned,
                    }
                )

            for car in cars:
                status = current_status(car, current_hour)
                status_writer.writerow(
                    {
                        "hour_ts": timestamp_text(current_hour),
                        "car_id": car["car_id"],
                        "zone_id": car["zone_id"],
                        "status": status,
                        "available_minutes": 60 if status == "available" else 0,
                        "in_ride_minutes": 60 if status == "in_ride" else 0,
                        "idle_minutes": 60 if status == "available" else 0,
                    }
                )

    metadata = {
        "dataset_label": "Synthetic portfolio data — not data from any real carsharing operator.",
        "seed": seed,
        "start": timestamp_text(start),
        "hours": hours,
        "car_count": car_count,
        "zone_count": len(zone_ids),
        "rides": generated_rides,
        "searches": generated_searches,
        "unserved_searches": generated_unserved,
        "timezone_assumption": "Europe/Moscow local clock; timestamps are timezone-naive for readability.",
    }
    (output_dir / "generation_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic carsharing inputs.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--start", default="2025-01-01 00:00:00")
    parser.add_argument("--hours", type=int, default=24 * 365)
    parser.add_argument("--cars", type=int, default=156)
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()
    metadata = run_generator(args.output_dir, datetime.fromisoformat(args.start), args.hours, args.cars, args.seed)
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
