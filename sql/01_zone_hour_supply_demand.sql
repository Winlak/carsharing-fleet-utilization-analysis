-- Hourly supply–demand mart.
-- Grain: one local hour × origin zone. Inputs are deterministic synthetic CSVs.
WITH bounds AS (
    SELECT
        MIN(CAST(hour_ts AS TIMESTAMP)) AS first_hour,
        MAX(CAST(hour_ts AS TIMESTAMP)) AS last_hour
    FROM car_statuses_hourly
),
calendar_hours AS (
    SELECT hour_ts
    FROM bounds,
         generate_series(first_hour, last_hour, INTERVAL 1 HOUR) AS series(hour_ts)
),
calendar_grid AS (
    SELECT calendar_hours.hour_ts, zones.zone_id
    FROM calendar_hours
    CROSS JOIN zones
),
status_by_hour AS (
    SELECT
        CAST(hour_ts AS TIMESTAMP) AS hour_ts,
        zone_id,
        SUM(available_minutes) AS available_car_minutes,
        SUM(in_ride_minutes) AS in_ride_minutes,
        SUM(idle_minutes) AS idle_minutes,
        COUNT(DISTINCT CASE WHEN status IN ('available', 'in_ride') THEN car_id END) AS active_cars
    FROM car_statuses_hourly
    GROUP BY 1, 2
),
rides_by_hour AS (
    SELECT
        date_trunc('hour', CAST(started_at AS TIMESTAMP)) AS hour_ts,
        origin_zone_id AS zone_id,
        COUNT(*) AS rides_started,
        SUM(duration_minutes) AS booked_ride_minutes
    FROM rides
    GROUP BY 1, 2
),
searches_by_hour AS (
    SELECT
        CAST(hour_ts AS TIMESTAMP) AS hour_ts,
        zone_id,
        MAX(starting_available_cars) AS starting_available_cars,
        SUM(searches) AS searches,
        SUM(bookings) AS bookings,
        SUM(unserved_searches) AS unserved_searches,
        SUM(abandoned_searches) AS abandoned_searches
    FROM searches_hourly
    GROUP BY 1, 2
),
completed_grid AS (
    SELECT
        grid.hour_ts,
        grid.zone_id,
        COALESCE(status.available_car_minutes, 0) AS available_car_minutes,
        COALESCE(status.in_ride_minutes, 0) AS in_ride_minutes,
        COALESCE(status.idle_minutes, 0) AS idle_minutes,
        COALESCE(status.active_cars, 0) AS active_cars,
        COALESCE(rides.rides_started, 0) AS rides_started,
        COALESCE(rides.booked_ride_minutes, 0) AS booked_ride_minutes,
        COALESCE(searches.starting_available_cars, 0) AS starting_available_cars,
        COALESCE(searches.searches, 0) AS searches,
        COALESCE(searches.bookings, 0) AS bookings,
        COALESCE(searches.unserved_searches, 0) AS unserved_searches,
        COALESCE(searches.abandoned_searches, 0) AS abandoned_searches
    FROM calendar_grid AS grid
    LEFT JOIN status_by_hour AS status
        ON grid.hour_ts = status.hour_ts AND grid.zone_id = status.zone_id
    LEFT JOIN rides_by_hour AS rides
        ON grid.hour_ts = rides.hour_ts AND grid.zone_id = rides.zone_id
    LEFT JOIN searches_by_hour AS searches
        ON grid.hour_ts = searches.hour_ts AND grid.zone_id = searches.zone_id
),
metrics AS (
    SELECT
        hour_ts,
        zone_id,
        CAST(hour_ts AS DATE) AS calendar_date,
        EXTRACT('hour' FROM hour_ts) AS hour_of_day,
        EXTRACT('isodow' FROM hour_ts) AS iso_weekday,
        CASE WHEN EXTRACT('isodow' FROM hour_ts) IN (6, 7) THEN 'weekend' ELSE 'weekday' END AS day_type,
        available_car_minutes,
        in_ride_minutes,
        idle_minutes,
        active_cars,
        rides_started,
        booked_ride_minutes,
        starting_available_cars,
        searches,
        bookings,
        unserved_searches,
        abandoned_searches,
        in_ride_minutes / NULLIF(in_ride_minutes + available_car_minutes, 0) AS utilization_rate,
        available_car_minutes / NULLIF(in_ride_minutes + available_car_minutes, 0) AS idle_rate,
        rides_started / NULLIF((in_ride_minutes + available_car_minutes) / 60.0, 0) AS rides_per_active_car,
        bookings / NULLIF(searches, 0) AS search_to_book_conversion,
        unserved_searches / NULLIF(searches, 0) AS lost_demand_proxy,
        searches / NULLIF(available_car_minutes / 60.0, 0) AS demand_pressure
    FROM completed_grid
)
SELECT
    metrics.*,
    LAG(available_car_minutes) OVER (
        PARTITION BY zone_id ORDER BY hour_ts
    ) AS previous_hour_available_car_minutes,
    AVG(search_to_book_conversion) OVER (
        PARTITION BY zone_id ORDER BY hour_ts ROWS BETWEEN 167 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_conversion,
    AVG(lost_demand_proxy) OVER (
        PARTITION BY zone_id ORDER BY hour_ts ROWS BETWEEN 167 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_lost_demand_proxy
FROM metrics
ORDER BY hour_ts, zone_id;
