"""Pandas analysis, prioritisation heuristic and reproducible visual outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PALETTE = {
    "ink": "#1F2937",
    "blue": "#2563EB",
    "gold": "#D97706",
    "pink": "#DB2777",
    "olive": "#718355",
    "grid": "#E5E7EB",
}


def ratio(numerator: pd.Series | float, denominator: pd.Series | float) -> pd.Series | float:
    if isinstance(numerator, pd.Series):
        return numerator.div(denominator).replace([np.inf, -np.inf], np.nan)
    return numerator / denominator if denominator else np.nan


def add_metric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["utilization_rate"] = ratio(result["in_ride_minutes"], result["in_ride_minutes"] + result["available_car_minutes"])
    result["idle_rate"] = ratio(result["idle_minutes"], result["in_ride_minutes"] + result["available_car_minutes"])
    result["rides_per_active_car"] = ratio(result["rides_started"], (result["in_ride_minutes"] + result["available_car_minutes"]) / 60)
    result["search_to_book_conversion"] = ratio(result["bookings"], result["searches"])
    result["lost_demand_proxy"] = ratio(result["unserved_searches"], result["searches"])
    return result


def aggregate(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    columns = [
        "available_car_minutes",
        "in_ride_minutes",
        "idle_minutes",
        "rides_started",
        "searches",
        "bookings",
        "unserved_searches",
        "abandoned_searches",
    ]
    return add_metric_columns(frame.groupby(by, as_index=False, observed=True)[columns].sum())


def configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": PALETTE["grid"],
            "axes.labelcolor": PALETTE["ink"],
            "xtick.color": PALETTE["ink"],
            "ytick.color": PALETTE["ink"],
            "axes.titleweight": "bold",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def make_figures(
    weekly: pd.DataFrame,
    zone_hour: pd.DataFrame,
    availability_curve: pd.DataFrame,
    weekday_weekend: pd.DataFrame,
    monthly: pd.DataFrame,
    priorities: pd.DataFrame,
    figures_dir: Path,
) -> None:
    configure_plotting()
    figures_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True, constrained_layout=True)
    axes[0].plot(weekly["week_start"], weekly["utilization_rate"] * 100, color=PALETTE["blue"], linewidth=2)
    axes[0].set_title("Утилизация парка по неделям")
    axes[0].set_ylabel("% serviceable time in ride")
    axes[0].grid(axis="y", color=PALETTE["grid"])
    axes[1].plot(weekly["week_start"], weekly["search_to_book_conversion"] * 100, color=PALETTE["gold"], linewidth=2, label="Конверсия")
    axes[1].plot(weekly["week_start"], weekly["lost_demand_proxy"] * 100, color=PALETTE["pink"], linewidth=2, label="Lost demand proxy")
    axes[1].set_title("Конверсия и потерянный спрос по неделям")
    axes[1].set_ylabel("% поисков")
    axes[1].legend(frameon=False, ncol=2)
    axes[1].grid(axis="y", color=PALETTE["grid"])
    fig.savefig(figures_dir / "weekly_fleet_metrics.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    heatmap = zone_hour.pivot_table(index="zone_name", columns="hour_of_day", values="lost_demand_proxy", aggfunc="mean")
    heatmap = heatmap.loc[heatmap.mean(axis=1).sort_values(ascending=False).index]
    fig, axis = plt.subplots(figsize=(14, 6), constrained_layout=True)
    image = axis.imshow(heatmap * 100, aspect="auto", cmap="magma")
    axis.set_title("Lost demand proxy: зона × час")
    axis.set_xlabel("Час начала поиска")
    axis.set_ylabel("Зона")
    axis.set_xticks(range(24))
    axis.set_yticks(range(len(heatmap.index)))
    axis.set_yticklabels(heatmap.index)
    colorbar = fig.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("Поиски без доступного автомобиля, %")
    fig.savefig(figures_dir / "zone_hour_lost_demand_heatmap.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    axis.plot(availability_curve["available_cars"], availability_curve["search_to_book_conversion"] * 100, marker="o", color=PALETTE["blue"], linewidth=2)
    axis.set_title("Конверсия по числу доступных автомобилей")
    axis.set_xlabel("Доступные автомобили в зоне в начале часа")
    axis.set_ylabel("Конверсия поиск → бронирование, %")
    axis.grid(axis="both", color=PALETTE["grid"])
    fig.savefig(figures_dir / "availability_conversion_relationship.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    weekday_weekend.plot.bar(x="day_type", y="utilization_rate", ax=axes[0], color=PALETTE["blue"], legend=False)
    axes[0].set_title("Утилизация: будни и выходные")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Доля serviceable времени")
    axes[0].set_ylim(0, max(0.35, weekday_weekend["utilization_rate"].max() * 1.25))
    weekday_weekend.plot.bar(x="day_type", y="lost_demand_proxy", ax=axes[1], color=PALETTE["pink"], legend=False)
    axes[1].set_title("Lost demand proxy: будни и выходные")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Доля поисков")
    axes[1].set_ylim(0, max(0.1, weekday_weekend["lost_demand_proxy"].max() * 1.25))
    for axis in axes:
        axis.grid(axis="y", color=PALETTE["grid"])
        axis.tick_params(axis="x", rotation=0)
    fig.savefig(figures_dir / "weekday_weekend_comparison.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    axes[0].plot(monthly["month"], monthly["utilization_rate"] * 100, marker="o", color=PALETTE["olive"], linewidth=2)
    axes[0].set_title("Сезонность утилизации")
    axes[0].set_ylabel("% serviceable time in ride")
    axes[0].tick_params(axis="x", rotation=45)
    axes[1].plot(monthly["month"], monthly["rides_started"], marker="o", color=PALETTE["gold"], linewidth=2)
    axes[1].set_title("Сезонность числа поездок")
    axes[1].set_ylabel("Поездки")
    axes[1].tick_params(axis="x", rotation=45)
    for axis in axes:
        axis.grid(axis="y", color=PALETTE["grid"])
    fig.savefig(figures_dir / "monthly_seasonality.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    # A self-contained static dashboard for GitHub and portfolio preview.
    fig = plt.figure(figsize=(16, 11), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, height_ratios=[1, 2.2, 2])
    kpi_axis = fig.add_subplot(grid[0, :])
    kpi_axis.axis("off")
    latest = weekly.iloc[-1]
    text = (
        "Синтетический кейс · Утилизация автопарка и баланс спроса\n"
        f"Утилизация: {weekly['utilization_rate'].mean():.1%}   |   "
        f"Конверсия: {weekly['search_to_book_conversion'].mean():.1%}   |   "
        f"Lost demand proxy: {weekly['lost_demand_proxy'].mean():.1%}   |   "
        f"Последняя неделя: {latest['rides_started']:,.0f} поездок"
    )
    kpi_axis.text(0.02, 0.55, text, fontsize=16, fontweight="bold", color=PALETTE["ink"], va="center")
    weekly_axis = fig.add_subplot(grid[1, 0])
    weekly_axis.plot(weekly["week_start"], weekly["utilization_rate"] * 100, color=PALETTE["blue"], label="Утилизация")
    weekly_axis.plot(weekly["week_start"], weekly["search_to_book_conversion"] * 100, color=PALETTE["gold"], label="Конверсия")
    weekly_axis.set_title("Динамика основных метрик")
    weekly_axis.set_ylabel("%")
    weekly_axis.legend(frameon=False)
    weekly_axis.grid(axis="y", color=PALETTE["grid"])
    heat_axis = fig.add_subplot(grid[1, 1])
    heat_axis.imshow(heatmap * 100, aspect="auto", cmap="magma")
    heat_axis.set_title("Где спрос теряется")
    heat_axis.set_xlabel("Час")
    heat_axis.set_yticks(range(len(heatmap.index)))
    heat_axis.set_yticklabels(heatmap.index, fontsize=8)
    heat_axis.set_xticks(range(0, 24, 3))
    table_axis = fig.add_subplot(grid[2, :])
    table_axis.axis("off")
    shown = priorities.head(7).copy()
    shown["priority_score"] = shown["priority_score"].round(0).astype(int)
    shown["lost_demand_proxy"] = (shown["lost_demand_proxy"] * 100).round(1).astype(str) + "%"
    shown["recommended_cars"] = shown["recommended_cars"].astype(int)
    table = table_axis.table(
        cellText=shown[["day_type", "hour_block", "recipient_zone", "donor_zone", "lost_demand_proxy", "recommended_cars", "priority_score"]].values,
        colLabels=["День", "Окно", "Получатель", "Донор", "Lost proxy", "Авто", "Приоритет"],
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)
    table_axis.set_title("Гипотезы релокации для тестирования", fontweight="bold", pad=12)
    fig.savefig(figures_dir / "fleet_utilization_dashboard.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def build_priorities(zone_hour: pd.DataFrame) -> pd.DataFrame:
    slots = zone_hour.copy()
    slots["hour_block"] = pd.cut(
        slots["hour_of_day"],
        bins=[-1, 6, 10, 16, 21, 23],
        labels=["ночь (00–06)", "утро (07–10)", "день (11–16)", "вечер (17–21)", "поздний вечер (22–23)"],
    )
    grouped = aggregate(slots, ["zone_id", "zone_name", "day_type", "hour_block"])
    grouped["idle_car_hours"] = grouped["idle_minutes"] / 60
    grouped["active_car_hours"] = (grouped["available_car_minutes"] + grouped["in_ride_minutes"]) / 60
    grouped["priority_score"] = grouped["unserved_searches"] + 0.35 * grouped["searches"] * (1 - grouped["search_to_book_conversion"].fillna(0))
    grouped["donor_score"] = grouped["idle_car_hours"] * (1 - grouped["utilization_rate"].fillna(0))
    recommendations: list[dict[str, object]] = []
    for (day_type, hour_block), block in grouped.groupby(["day_type", "hour_block"], observed=True):
        recipients = block.sort_values(["priority_score", "unserved_searches"], ascending=False).head(3)
        donors = block.sort_values(["donor_score", "idle_car_hours"], ascending=False)
        for _, recipient in recipients.iterrows():
            donor_options = donors[donors["zone_id"] != recipient["zone_id"]]
            if donor_options.empty or recipient["unserved_searches"] <= 0:
                continue
            donor = donor_options.iloc[0]
            recommended_cars = int(np.clip(np.ceil(recipient["unserved_searches"] / 550), 1, 3))
            recommendations.append(
                {
                    "day_type": day_type,
                    "hour_block": str(hour_block),
                    "recipient_zone": recipient["zone_name"],
                    "donor_zone": donor["zone_name"],
                    "unserved_searches": int(recipient["unserved_searches"]),
                    "search_to_book_conversion": recipient["search_to_book_conversion"],
                    "lost_demand_proxy": recipient["lost_demand_proxy"],
                    "recipient_idle_car_hours": recipient["idle_car_hours"],
                    "donor_idle_car_hours": donor["idle_car_hours"],
                    "recommended_cars": recommended_cars,
                    "priority_score": recipient["priority_score"],
                    "decision_note": "Гипотеза для рандомизированного пилота, не оценка причинного эффекта.",
                }
            )
    return pd.DataFrame(recommendations).sort_values("priority_score", ascending=False).reset_index(drop=True)


def run_analysis(processed_dir: Path, raw_dir: Path, outputs_dir: Path) -> dict[str, object]:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = outputs_dir / "figures"
    hour = pd.read_csv(processed_dir / "mart_zone_hour.csv", parse_dates=["hour_ts", "calendar_date"])
    zones = pd.read_csv(raw_dir / "zones.csv")
    # Deliberate pandas operations: load, filter, groupby, merge and recalculation from numerators.
    zone_hour = hour.merge(zones[["zone_id", "zone_name", "zone_type"]], on="zone_id", how="left", validate="many_to_one")
    if zone_hour["zone_name"].isna().any():
        raise ValueError("Zone join did not cover all hourly records")
    # This is observed before the search outcomes of the hour are simulated;
    # it avoids using the same-hour booking result as a supply predictor.
    zone_hour["available_cars"] = zone_hour["starting_available_cars"]
    zone_hour["week_start"] = zone_hour["hour_ts"].dt.to_period("W-MON").apply(lambda period: period.start_time)
    zone_hour["month"] = zone_hour["hour_ts"].dt.to_period("M").astype(str)

    weekly = aggregate(zone_hour, ["week_start"])
    monthly = aggregate(zone_hour, ["month"])
    weekday_weekend = aggregate(zone_hour, ["day_type"])
    availability_curve = aggregate(zone_hour[zone_hour["searches"] > 0], ["available_cars"])
    availability_curve = availability_curve[(availability_curve["available_cars"] <= 20) & (availability_curve["searches"] >= 50)]
    priorities = build_priorities(zone_hour)

    weekly.to_csv(outputs_dir / "weekly_metrics.csv", index=False)
    monthly.to_csv(outputs_dir / "monthly_metrics.csv", index=False)
    weekday_weekend.to_csv(outputs_dir / "weekday_weekend_metrics.csv", index=False)
    availability_curve.to_csv(outputs_dir / "availability_conversion_curve.csv", index=False)
    priorities.to_csv(outputs_dir / "priority_relocations.csv", index=False)

    make_figures(weekly, zone_hour, availability_curve, weekday_weekend, monthly, priorities, figures_dir)

    totals = aggregate(zone_hour, []) if False else add_metric_columns(pd.DataFrame([zone_hour[[
        "available_car_minutes", "in_ride_minutes", "idle_minutes", "rides_started", "searches", "bookings", "unserved_searches", "abandoned_searches"
    ]].sum()]))
    correlation = zone_hour.loc[zone_hour["searches"] >= 2, ["available_cars", "search_to_book_conversion"]].corr(method="spearman").iloc[0, 1]
    top_priority = priorities.iloc[0].to_dict() if not priorities.empty else {}
    summary = {
        "data_label": "Synthetic portfolio dataset; not data from a real carsharing operator.",
        "time_window": f"{zone_hour['hour_ts'].min():%Y-%m-%d} — {zone_hour['hour_ts'].max():%Y-%m-%d}",
        "fleet_size": int(pd.read_csv(raw_dir / "cars.csv").shape[0]),
        "zones": int(zones.shape[0]),
        "rides": int(totals.loc[0, "rides_started"]),
        "searches": int(totals.loc[0, "searches"]),
        "utilization_rate": float(totals.loc[0, "utilization_rate"]),
        "available_car_minutes": int(totals.loc[0, "available_car_minutes"]),
        "rides_per_active_car": float(totals.loc[0, "rides_per_active_car"]),
        "search_to_book_conversion": float(totals.loc[0, "search_to_book_conversion"]),
        "lost_demand_proxy": float(totals.loc[0, "lost_demand_proxy"]),
        "availability_conversion_spearman": float(correlation),
        "top_relocation_hypothesis": top_priority,
    }
    (outputs_dir / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    chart_map = """# Карта визуализаций

PNG ниже создаются локально для просмотра после `make reproduce`, но намеренно исключены из Git: байты Matplotlib могут отличаться между платформами. Канонические, версионируемые визуальные артефакты — self-contained [`fleet_dashboard.html`](../../artifacts/fleet_dashboard.html) и [`analysis_report.html`](../../artifacts/analysis_report.html).

| Файл | Вопрос | Тип | Поддерживаемый вывод |
|---|---|---|---|
| `weekly_fleet_metrics.png` | Меняются ли ключевые метрики во времени? | Линии | Сезонность и динамика конверсии/потерь. |
| `zone_hour_lost_demand_heatmap.png` | В каких сочетаниях зоны и часа нет предложения? | Тепловая карта | Поиск окон для пилота релокации. |
| `availability_conversion_relationship.png` | Как совместно меняются доступность и конверсия? | Линия по бакетам доступности | Описательная связь, не причинный эффект. |
| `weekday_weekend_comparison.png` | Отличается ли режим спроса в выходные? | Столбцы | Нужны раздельные правила планирования. |
| `monthly_seasonality.png` | Есть ли сезонность? | Линии | Не переносить один месяц на весь год. |
| `fleet_utilization_dashboard.png` | Что смотреть в одном операционном обзоре? | Статический дашборд | Приоритеты и состояние supply–demand. |
"""
    (outputs_dir / "chart_map.md").write_text(chart_map, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pandas analysis and save portfolio artifacts.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--outputs-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    summary = run_analysis(args.processed_dir, args.raw_dir, args.outputs_dir)
    print(json.dumps(summary, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
