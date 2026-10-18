"""Render the reader-facing Markdown report from reviewed output tables."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def pct(value: float) -> str:
    return f"{value:.1%}"


def render_report(outputs_dir: Path, docs_dir: Path) -> None:
    summary = json.loads((outputs_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    priorities = pd.read_csv(outputs_dir / "priority_relocations.csv").head(6)
    weekday_weekend = pd.read_csv(outputs_dir / "weekday_weekend_metrics.csv")
    monthly = pd.read_csv(outputs_dir / "monthly_metrics.csv")
    top = summary["top_relocation_hypothesis"]
    busy_month = monthly.loc[monthly["rides_started"].idxmax()]
    quiet_month = monthly.loc[monthly["rides_started"].idxmin()]
    weekday = weekday_weekend.set_index("day_type")
    priority_table = "\n".join(
        "| {day_type} | {hour_block} | {donor_zone} → {recipient_zone} | {lost_demand_proxy:.1%} | {recommended_cars} |".format(**row)
        for row in priorities.to_dict("records")
    )
    report = f"""# Утилизация автопарка и баланс спроса

> **Портфельный кейс на синтетических данных.** Все записи сгенерированы `src/generate_data.py` с фиксированным seed; это не данные Делимобиля или другого оператора.

## Краткие результаты

- **Предложение не покрывает часть намерения пользователя.** За {summary['time_window']} выполнено {summary['rides']:,} синтетических поездок; lost demand proxy составил {pct(summary['lost_demand_proxy'])} поисков. Это консервативный индикатор: он считает только сессии, в которых в исходной зоне не было доступного автомобиля.
- **Баланс спроса важнее средней загрузки.** Утилизация составляет {pct(summary['utilization_rate'])}, а конверсия поиска в бронирование — {pct(summary['search_to_book_conversion'])}. Средние показатели скрывают острые окна «зона × час», поэтому решение должно быть адресным, а не городским усреднением.
- **Первой тестовой гипотезой станет перемещение {top.get('recommended_cars', '—')} автомобилей.** Для окна «{top.get('day_type', '—')} / {top.get('hour_block', '—')}» кандидат-донор — **{top.get('donor_zone', '—')}**, получатель — **{top.get('recipient_zone', '—')}**. Это ранжирование наблюдательное; эффект требуется проверить экспериментом.

## Что именно измеряется

Витрина имеет зерно **«локальный час × зона происхождения»**. `available-car minutes` — минуты статуса `available`; serviceable-время — `available + in_ride`. Поэтому `utilization rate = in_ride minutes / serviceable minutes`, а `rides per active car = rides / serviceable car-hours`.

`search-to-book conversion = bookings / searches`. `lost demand proxy = searches without an available car / searches`. Простои показаны через `idle_minutes` и `idle_rate = idle / serviceable time`. Машины в charging, maintenance и relocating исключены из serviceable-знаменателя: их невозможно показать пользователю в этом часу.

## Динамика подтверждает необходимость планирования по времени

Интерактивная версия динамики и остальных графиков доступна в [portable dashboard](../artifacts/fleet_dashboard.html). Локальные PNG также создаются при `make reproduce`, однако намеренно не версионируются: их байты зависят от платформы отрисовки и не являются каноническим артефактом кейса.

**Ни одна неделя не должна считаться универсальным базисом.** В синтетическом сценарии объём поездок достигает максимума в {busy_month['month']} ({busy_month['rides_started']:,} поездок), а минимален в {quiet_month['month']} ({quiet_month['rides_started']:,}). Это заданная генератором сезонность, но она иллюстрирует правильный аналитический принцип: для оценки пилота нужны равные календарные недели и стратификация по day type.

## Дефицит концентрируется в конкретных сочетаниях зоны и часа

**Тепловая карта — инструмент выбора страты для теста, а не причинное доказательство.** Она показывает долю поисков, встретивших нулевую доступность. Для проверки результата в боевых данных понадобятся ETA, радиус поиска, стоимость, отмены и реальная логика выдачи автомобиля.

**Доступность и конверсия движутся вместе в агрегированных наблюдениях** (Spearman ρ = {summary['availability_conversion_spearman']:.2f}). Для этого среза availability фиксируется до обработки поисков часа, поэтому исход бронирования не подставляется обратно в предиктор. Но это всё ещё не отделяет эффект доступности от спроса, цены, состава пользователей и времени суток; причинный вывод здесь делать нельзя.

## Будни и выходные — разные операционные режимы

**Слоты следует планировать отдельно.** В симуляции утилизация в будни — {pct(weekday.loc['weekday', 'utilization_rate'])}, в выходные — {pct(weekday.loc['weekend', 'utilization_rate'])}; lost demand proxy соответственно {pct(weekday.loc['weekday', 'lost_demand_proxy'])} и {pct(weekday.loc['weekend', 'lost_demand_proxy'])}. Поэтому контроль и treatment нельзя смешивать без стратификации.

## Приоритеты релокации: кандидаты для теста

Рейтинг соединяет потенциального получателя с донором **в том же типе дня и временном окне**. Приоритет растёт с числом не обслуженных поисков и общим объёмом незавершённых сессий; донор выбирается по избытку idle car-hours. Количество автомобилей ограничено 1–3, чтобы не перенастраивать сеть одной итерацией.

| День | Окно | Донор → получатель | Lost demand proxy | Автомобилей |
|---|---|---|---:|---:|
{priority_table}

**Операционное действие:** начать с верхних 2–3 комбинаций, не со всех строк одновременно. До запуска следует вручную проверить физическую осуществимость: время и стоимость перемещения, парковочные ограничения и ожидаемая доступность донорской зоны.

## Дизайн пилота: как проверить гипотезу честно

1. **Единица рандомизации:** `зона × временное окно × дата`, стратифицированная по weekday/weekend. В treatment заранее перемещается 1–3 авто; в control действуют текущие правила.
2. **Горизонт:** минимум 4 полные недели после 2 недель pre-period. Не останавливать тест по промежуточному значению без заранее заданного правила.
3. **Primary success:** рост search-to-book conversion минимум на 3 п.п. против контрольных слотов; 95% доверительный интервал для treatment–control (кластерный bootstrap по дате × зоне) должен исключать ноль. Одновременно проверять абсолютное число завершённых бронирований.
4. **Основной риск:** улучшить получателя ценой донора. Guardrails: рост lost demand proxy в донорских слотах не более 1 п.п. (верхняя граница 95% CI), городской объём поездок не падает более чем на 2%, а доля relocating/charging-часов не растёт без операционного обоснования.
5. **Анализ:** intention-to-treat; сравнить pre/post изменения treatment и control внутри страт. Не объявлять причинный успех при нарушении рандомизации, массовых отменах или изменении цены/промо в одной из групп.

## Что проверить дальше

- Сколько фактических поисков прекращается до экрана доступных автомобилей? Это определит смещение lost demand proxy.
- Как меняются ETA, отмены и цена вместе с доступностью? Эти факторы могут объяснить часть ассоциации с конверсией.
- Какова стоимость и углеродный след релокации относительно добавочных поездок?

## Caveats and assumptions

- Синтетическая генерация намеренно задаёт сезонность и поведенческие вероятности; результаты демонстрируют метод, а не рыночную оценку.
- Почасовой статус округляет внутрисчасовую занятость до статусного часа, поэтому availability и utilization следует воспринимать как управленную витрину, а не телематику поминутного уровня.
- `lost_demand_proxy` — не полный unmet demand, а наблюдаемый нижний предел.
- В кейсе нет отмен, цены, ETA, расстояния до автомобиля, парковочных правил и выручки; они обязательны для production-решения.

Методология, SQL и качество данных: [`README`](../README.md), [`data dictionary`](data_dictionary.md), [`quality checks`](../data/processed/data_quality_report.md), [`notebook source`](../notebooks/fleet_utilization_analysis.ipynb), [`interactive report`](../artifacts/analysis_report.html).
"""
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "analysis_report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    render_report(root / "outputs", root / "docs")
