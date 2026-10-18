"""Create canonical snapshot-first artifacts for portable report and dashboard HTML."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    clean = frame.where(pd.notna(frame), None).copy()
    for column in clean.select_dtypes(include=["datetime64[ns]"]).columns:
        clean[column] = clean[column].dt.strftime("%Y-%m-%d")
    return json.loads(clean.to_json(orient="records", force_ascii=False))


def source_objects(root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    hourly_sql = (root / "sql" / "01_zone_hour_supply_demand.sql").read_text(encoding="utf-8")
    daily_sql = (root / "sql" / "03_fleet_daily_summary.sql").read_text(encoding="utf-8")
    manifest_sources = [
        {"id": "zone_hour_mart", "label": "Synthetic hourly supply–demand mart", "path": "sql/01_zone_hour_supply_demand.sql"},
        {"id": "fleet_daily_mart", "label": "Synthetic fleet daily mart", "path": "sql/03_fleet_daily_summary.sql"},
    ]
    sources = [
        {
            "id": "zone_hour_mart",
            "query": {
                "engine": "DuckDB",
                "sql": hourly_sql,
                "description": "Calendar-complete hourly synthetic supply, rides and search funnel by origin zone.",
                "tables_used": [
                    "data/raw/car_statuses_hourly.csv",
                    "data/raw/rides.csv",
                    "data/raw/searches_hourly.csv",
                    "data/raw/zones.csv",
                ],
                "filters": ["2025 synthetic local-hour data", "all generated zones", "no real customer or operator data"],
                "executed_at": "2026-08-12T00:00:00Z",
                "language": "sql",
            },
        },
        {
            "id": "fleet_daily_mart",
            "query": {
                "engine": "DuckDB",
                "sql": daily_sql,
                "description": "Fleet roll-up recalculates rates from components rather than averaging zone rates.",
                "tables_used": ["data/processed/mart_zone_hour.csv"],
                "filters": ["2025 synthetic local-day data"],
                "executed_at": "2026-08-12T00:00:00Z",
                "language": "sql",
            },
        },
    ]
    return manifest_sources, sources


def chart_definitions() -> list[dict[str, object]]:
    return [
        {
            "id": "weekly_trend_chart",
            "title": "Weekly utilization and conversion",
            "subtitle": "Synthetic 2025 data; rates are recalculated from weekly numerators and denominators.",
            "type": "line",
            "dataset": "weekly_trend",
            "sourceId": "fleet_daily_mart",
            "encodings": {
                "x": {"field": "week_start", "type": "temporal"},
                "y": {"field": "rate", "type": "quantitative"},
                "color": {"field": "metric", "type": "nominal"},
            },
        },
        {
            "id": "lost_demand_by_zone_chart",
            "title": "Lost demand proxy by zone",
            "subtitle": "Share of searches that had no available car in the origin zone; full 2025 synthetic period.",
            "type": "bar",
            "dataset": "zone_loss",
            "sourceId": "zone_hour_mart",
            "encodings": {
                "x": {"field": "zone_name", "type": "nominal"},
                "y": {"field": "lost_demand_proxy", "type": "quantitative"},
            },
        },
    ]


def build_artifacts(root: Path) -> None:
    outputs = root / "outputs"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    summary = json.loads((outputs / "analysis_summary.json").read_text(encoding="utf-8"))
    weekly = pd.read_csv(outputs / "weekly_metrics.csv")
    priorities = pd.read_csv(outputs / "priority_relocations.csv").head(12)
    zone_hour = pd.read_csv(root / "data" / "processed" / "mart_zone_hour.csv")
    zones = pd.read_csv(root / "data" / "raw" / "zones.csv")
    zone_loss = (
        zone_hour.merge(zones[["zone_id", "zone_name"]], on="zone_id", how="left", validate="many_to_one")
        .groupby("zone_name", as_index=False)[["searches", "unserved_searches"]]
        .sum()
    )
    zone_loss["lost_demand_proxy"] = zone_loss["unserved_searches"] / zone_loss["searches"]
    zone_loss = zone_loss.sort_values("lost_demand_proxy", ascending=False)
    weekly_trend = pd.concat(
        [
            weekly[["week_start", "utilization_rate"]].rename(columns={"utilization_rate": "rate"}).assign(metric="Utilization"),
            weekly[["week_start", "search_to_book_conversion"]]
            .rename(columns={"search_to_book_conversion": "rate"})
            .assign(metric="Search-to-book conversion"),
        ],
        ignore_index=True,
    )
    manifest_sources, sources = source_objects(root)
    charts = chart_definitions()
    datasets = {
        "weekly_trend": records(weekly_trend),
        "zone_loss": records(zone_loss),
        "priority_relocations": records(priorities),
        "headline": [
            {
                "utilization_rate": summary["utilization_rate"],
                "search_to_book_conversion": summary["search_to_book_conversion"],
                "lost_demand_proxy": summary["lost_demand_proxy"],
                "rides": summary["rides"],
            }
        ],
    }
    common = {
        "version": 1,
        "title": "Утилизация автопарка и баланс спроса",
        "generatedAt": "2026-08-12T00:00:00Z",
        "charts": charts,
        "tables": [
            {
                "id": "priority_table",
                "title": "Hypotheses for relocation pilot",
                "subtitle": "Ranked opportunities; not estimated causal impact.",
                "dataset": "priority_relocations",
                "sourceId": "zone_hour_mart",
                "defaultSort": {"field": "priority_score", "direction": "desc"},
                "columns": [
                    {"field": "day_type", "label": "Day type"},
                    {"field": "hour_block", "label": "Time window"},
                    {"field": "recipient_zone", "label": "Recipient"},
                    {"field": "donor_zone", "label": "Donor"},
                    {"field": "lost_demand_proxy", "label": "Lost demand proxy", "format": "percent"},
                    {"field": "recommended_cars", "label": "Cars", "format": "number"},
                    {"field": "priority_score", "label": "Priority score", "format": "number"},
                ],
            }
        ],
        "sources": manifest_sources,
    }
    report_manifest = {
        **common,
        "surface": "report",
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Утилизация автопарка и баланс спроса"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "sourceId": "zone_hour_mart",
                "body": (
                    "## Краткие результаты\n\n"
                    f"- **{summary['lost_demand_proxy']:.1%} поисков** завершились без автомобиля в исходной зоне.\n"
                    f"- **Утилизация {summary['utilization_rate']:.1%}** и конверсия **{summary['search_to_book_conversion']:.1%}** скрывают концентрированные дефициты.\n"
                    "- Релокации — экспериментальная гипотеза: наблюдательные связи не доказывают причинный эффект."
                ),
            },
            {
                "id": "finding_weekly",
                "type": "markdown",
                "sourceId": "fleet_daily_mart",
                "body": "## Сезонность и динамика\n\n**Сравнивать слоты нужно с одинаковым календарным контекстом.** Недельные метрики меняются вместе с заданной сезонностью спроса.",
            },
            {"id": "weekly_trend", "type": "chart", "chartId": "weekly_trend_chart"},
            {
                "id": "finding_loss",
                "type": "markdown",
                "sourceId": "zone_hour_mart",
                "body": "## Где начинать пилот\n\n**Lost demand proxy ранжирует окна для тестирования, а не размер причинного эффекта.** В production-версии потребуются ETA, цена, отмены и радиус доступности.",
            },
            {"id": "zone_loss", "type": "chart", "chartId": "lost_demand_by_zone_chart"},
            {
                "id": "recommendations",
                "type": "markdown",
                "body": "## Следующий шаг\n\nЗапустить стратифицированный 4-недельный пилот с allocation 1–3 авто. Primary metric: search-to-book conversion; guardrail: lost demand proxy в зоне-доноре.",
            },
            {"id": "priority_table", "type": "table", "tableId": "priority_table"},
            {
                "id": "caveats",
                "type": "markdown",
                "body": "## Caveats and assumptions\n\nДанные синтетические. Почасовой статус округляет внутрисчасовую занятость. Lost demand proxy — нижняя граница ненаблюдаемого спроса; не делать причинных выводов без эксперимента.",
            },
        ],
    }
    dashboard_cards = [
        {
            "id": "utilization_card",
            "dataset": "headline",
            "sourceId": "zone_hour_mart",
            "metrics": [{"label": "Utilization", "field": "utilization_rate", "format": "percent"}],
            "description": "In-ride share of serviceable car-minutes.",
        },
        {
            "id": "conversion_card",
            "dataset": "headline",
            "sourceId": "zone_hour_mart",
            "metrics": [{"label": "Search-to-book conversion", "field": "search_to_book_conversion", "format": "percent"}],
            "description": "Bookings divided by synthetic car searches.",
        },
        {
            "id": "lost_demand_card",
            "dataset": "headline",
            "sourceId": "zone_hour_mart",
            "metrics": [{"label": "Lost demand proxy", "field": "lost_demand_proxy", "format": "percent"}],
            "description": "Searches with no available origin-zone car.",
        },
        {
            "id": "rides_card",
            "dataset": "headline",
            "sourceId": "zone_hour_mart",
            "metrics": [{"label": "Rides", "field": "rides", "format": "number"}],
            "description": "Synthetic rides started in the full period.",
        },
    ]
    dashboard_manifest = {
        **common,
        "surface": "dashboard",
        "cards": dashboard_cards,
        "blocks": [
            {"id": "dashboard_intro", "type": "markdown", "body": "# Утилизация автопарка и баланс спроса\n\nСинтетический snapshot за 2025 год; не данные реального оператора."},
            {"id": "metrics", "type": "metric-strip", "cardIds": [card["id"] for card in dashboard_cards]},
            {"id": "weekly_trend", "type": "chart", "chartId": "weekly_trend_chart"},
            {"id": "zone_loss", "type": "chart", "chartId": "lost_demand_by_zone_chart"},
            {"id": "priority_text", "type": "markdown", "body": "## Приоритеты релокации\n\nТаблица показывает кандидатов для рандомизированного пилота. Не интерпретировать ranking как причинный эффект."},
            {"id": "priority_table", "type": "table", "tableId": "priority_table"},
        ],
    }
    for name, surface, manifest in [
        ("analysis_report_artifact.json", "report", report_manifest),
        ("fleet_dashboard_artifact.json", "dashboard", dashboard_manifest),
    ]:
        payload = {
            "surface": surface,
            "manifest": manifest,
            "snapshot": {"version": 1, "generatedAt": "2026-08-12T00:00:00Z", "status": "ready", "datasets": datasets},
            "sources": sources,
        }
        (artifacts / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_artifacts(Path(__file__).resolve().parents[1])
