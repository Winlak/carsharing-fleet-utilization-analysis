-- Daily zone mart built from the canonical hourly mart.
WITH zone_daily AS (
    SELECT
        calendar_date,
        zone_id,
        SUM(available_car_minutes) AS available_car_minutes,
        SUM(in_ride_minutes) AS in_ride_minutes,
        SUM(idle_minutes) AS idle_minutes,
        SUM(rides_started) AS rides_started,
        SUM(searches) AS searches,
        SUM(bookings) AS bookings,
        SUM(unserved_searches) AS unserved_searches,
        SUM(abandoned_searches) AS abandoned_searches
    FROM mart_zone_hour
    GROUP BY 1, 2
),
daily_metrics AS (
    SELECT
        calendar_date,
        zone_id,
        available_car_minutes,
        in_ride_minutes,
        idle_minutes,
        rides_started,
        searches,
        bookings,
        unserved_searches,
        abandoned_searches,
        in_ride_minutes / NULLIF(in_ride_minutes + available_car_minutes, 0) AS utilization_rate,
        rides_started / NULLIF((in_ride_minutes + available_car_minutes) / 60.0, 0) AS rides_per_active_car,
        bookings / NULLIF(searches, 0) AS search_to_book_conversion,
        unserved_searches / NULLIF(searches, 0) AS lost_demand_proxy
    FROM zone_daily
)
SELECT
    daily_metrics.*,
    LAG(utilization_rate) OVER (
        PARTITION BY zone_id ORDER BY calendar_date
    ) AS prior_day_utilization_rate,
    AVG(utilization_rate) OVER (
        PARTITION BY zone_id ORDER BY calendar_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_utilization_rate,
    RANK() OVER (
        PARTITION BY calendar_date ORDER BY lost_demand_proxy DESC NULLS LAST
    ) AS daily_lost_demand_rank
FROM daily_metrics;
