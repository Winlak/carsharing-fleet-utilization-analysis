# Data dictionary

Все таблицы ниже являются синтетическими и создаются локально генератором.

| Таблица | Зерно | Ключевые поля | Назначение |
|---|---|---|---|
| `zones.csv` | зона | `zone_id`, `zone_name`, `zone_type`, `demand_weight` | Справочник 12 условных городских зон. Координаты декоративны и не привязаны к реальной сети. |
| `cars.csv` | автомобиль | `car_id`, `initial_zone_id`, `model_group` | Синтетический автопарк из 156 автомобилей. |
| `car_statuses_hourly.csv` | час × автомобиль | `hour_ts`, `car_id`, `zone_id`, `status` | Почасовой статус: `available`, `in_ride`, `maintenance`, `charging`, `relocating`. |
| `rides.csv` | поездка | `ride_id`, `car_id`, `started_at`, `ended_at`, `origin_zone_id` | События забронированных поездок. |
| `searches_hourly.csv` | час × зона | `starting_available_cars`, `searches`, `bookings`, `unserved_searches`, `abandoned_searches` | Воронка поиска до бронирования; availability зафиксирована до результатов поисков этого часа. |
| `mart_zone_hour.csv` | час × зона | supply, rides, funnel и rates | Главная SQL-витрина для поиска дефицита. |
| `mart_zone_daily.csv` | день × зона | дневные компоненты и окна | Сезонность и ежедневное сравнение. |
| `mart_fleet_daily.csv` | день | агрегированные компоненты | Уровень города; ставки пересчитываются из числителей/знаменателей. |

## Статусы и минутные поля

- `available_minutes`: 60 только при `available`; это доступное для показа клиенту время.
- `in_ride_minutes`: 60 только при `in_ride`; применяется в числителе utilization.
- `idle_minutes`: равно `available_minutes` в этой упрощённой модели.
- Почасовая модель округляет занятую внутри часа машину до статусного часа. Это осознанное ограничение, а не ошибка точности телематики.
- `starting_available_cars`: число машин, доступных до обработки поисков часа. Используется только для описательной связи доступности и конверсии, чтобы не подставлять исход бронирования обратно в предиктор.

## Метрики

| Метрика | Формула | Интерпретация |
|---|---|---|
| Utilization rate | `in_ride_minutes / (in_ride_minutes + available_car_minutes)` | Доля serviceable-времени в поездке. Charging/maintenance/relocating исключены. |
| Available-car minutes | `SUM(available_minutes)` | Доступное предложение в зоне за период. |
| Rides per active car | `rides_started / ((in_ride + available) / 60)` | Поездки на serviceable car-hour. |
| Search-to-book conversion | `bookings / searches` | Доля поисков, завершившихся бронированием. |
| Lost demand proxy | `unserved_searches / searches` | Нижняя граница потерь: нулевая доступность в origin-зоне. |
| Idle rate | `idle_minutes / (in_ride + available)` | Доля serviceable-времени, простоявшая доступной. |
