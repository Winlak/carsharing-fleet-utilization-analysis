"""Create a deterministic notebook source and execute an ignored runtime copy."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import nbformat as nbf


def build_notebook(summary: dict[str, object]) -> nbf.NotebookNode:
    top_priority = summary.get("top_relocation_hypothesis", {})
    notebook = nbf.v4.new_notebook()
    notebook.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
    notebook.metadata.language_info = {"name": "python", "version": "3"}
    notebook.cells = [
        nbf.v4.new_markdown_cell(
            "# Утилизация автопарка и баланс спроса\n\n"
            "**Данные синтетические и воспроизводимые.** Это портфельный кейс; он не использует и не описывает данные реального каршеринга."
        ),
        nbf.v4.new_markdown_cell(
            "## tl;dr\n\n"
            f"- В моделируемом периоде: **{summary['rides']:,} поездок**, утилизация **{summary['utilization_rate']:.1%}** и конверсия поиска в бронирование **{summary['search_to_book_conversion']:.1%}**.\n"
            f"- Lost demand proxy — **{summary['lost_demand_proxy']:.1%}** поисков без доступного автомобиля в зоне; это нижняя граница, а не полная оценка спроса.\n"
            f"- Первая гипотеза релокации: **{top_priority.get('donor_zone', '—')} → {top_priority.get('recipient_zone', '—')}**, {top_priority.get('hour_block', '—')}. Это кандидат для рандомизированного теста, а не доказанный эффект."
        ),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "### Key Assumptions\n\n"
            "- Период: 2025 год, локальные часы Europe/Moscow; генератор фиксирован seed.\n"
            "- Доступность и занятость агрегированы до почасового статуса: поездка, начатая в час, занимает статусный час.\n"
            "- `lost_demand_proxy` = поиски в зоне без доступного автомобиля / все поиски. Он не включает пользователей, которые не открыли приложение.\n"
            "- Наблюдаемая связь доступности и конверсии не интерпретируется как причинная."
        ),
        nbf.v4.new_markdown_cell("## Data"),
        nbf.v4.new_markdown_cell("### 1. Load marts and join zone metadata"),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n"
            "\n"
            "ROOT = Path.cwd().resolve()\n"
            "if not (ROOT / 'data').exists():\n"
            "    ROOT = ROOT.parent\n"
            "processed = ROOT / 'data' / 'processed'\n"
            "raw = ROOT / 'data' / 'raw'\n"
            "hour = pd.read_csv(processed / 'mart_zone_hour.csv', parse_dates=['hour_ts'])\n"
            "zones = pd.read_csv(raw / 'zones.csv')\n"
            "zone_hour = hour.merge(zones[['zone_id', 'zone_name', 'zone_type']], on='zone_id', how='left', validate='many_to_one')\n"
            "assert zone_hour['zone_name'].notna().all()\n"
            "zone_hour[['hour_ts', 'zone_name', 'available_car_minutes', 'rides_started', 'searches']].head()"
        ),
        nbf.v4.new_markdown_cell("### 2. Validate grain and metric components"),
        nbf.v4.new_code_cell(
            "assert len(zone_hour) == zone_hour['hour_ts'].nunique() * zone_hour['zone_id'].nunique()\n"
            "assert (zone_hour[['available_car_minutes', 'in_ride_minutes', 'searches']] >= 0).all().all()\n"
            "zone_hour.groupby('status' if 'status' in zone_hour else 'day_type').size().head()"
        ),
        nbf.v4.new_markdown_cell("## Results"),
        nbf.v4.new_markdown_cell("### 3. Recalculate weekday/weekend metrics from numerators and denominators"),
        nbf.v4.new_code_cell(
            "components = ['available_car_minutes', 'in_ride_minutes', 'rides_started', 'searches', 'bookings', 'unserved_searches']\n"
            "day_type = zone_hour.groupby('day_type', as_index=False)[components].sum()\n"
            "day_type['utilization_rate'] = day_type['in_ride_minutes'] / (day_type['in_ride_minutes'] + day_type['available_car_minutes'])\n"
            "day_type['conversion'] = day_type['bookings'] / day_type['searches']\n"
            "day_type['lost_demand_proxy'] = day_type['unserved_searches'] / day_type['searches']\n"
            "day_type[['day_type', 'utilization_rate', 'conversion', 'lost_demand_proxy']]"
        ),
        nbf.v4.new_markdown_cell("### 4. Availability and conversion (descriptive, not causal)"),
        nbf.v4.new_code_cell(
            "curve = (zone_hour.query('searches > 0')\n"
            "    .assign(available_cars=lambda x: x['starting_available_cars'])\n"
            "    .groupby('available_cars', as_index=False)[['bookings', 'searches']].sum())\n"
            "curve['conversion'] = curve['bookings'] / curve['searches']\n"
            "curve = curve.query('available_cars <= 20')\n"
            "ax = curve.plot(x='available_cars', y='conversion', marker='o', color='#2563EB', legend=False, figsize=(8, 4))\n"
            "ax.set(title='Конверсия по доступности', xlabel='Доступные автомобили', ylabel='Конверсия поиск → бронирование')\n"
            "plt.show()"
        ),
        nbf.v4.new_markdown_cell("### 5. Inspect relocation hypotheses"),
        nbf.v4.new_code_cell(
            "priorities = pd.read_csv(ROOT / 'outputs' / 'priority_relocations.csv')\n"
            "priorities[['day_type', 'hour_block', 'recipient_zone', 'donor_zone', 'lost_demand_proxy', 'recommended_cars', 'priority_score']].head(10)"
        ),
        nbf.v4.new_markdown_cell(
            "## Takeaways\n\n"
            "- Использовать релокацию как экспериментальную гипотезу в самых напряжённых `зона × окно` и измерять её против стратифицированного контроля.\n"
            "- Не переносить автомобили из зоны-донора, если в ней растёт lost demand proxy: это guardrail, а не побочный показатель.\n"
            "- Для боевого решения нужны фактическая география, отмены, ETA, цена, свободные автомобили в радиусе и причина неуспешного бронирования."
        ),
    ]
    for index, cell in enumerate(notebook.cells, start=1):
        cell.id = f"fleet-{index:02d}"
    return notebook


def write_notebook(summary_path: Path, notebook_path: Path) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(build_notebook(summary), notebook_path)


def execute_notebook(notebook_path: Path, execution_dir: Path, project_root: Path) -> Path:
    """Execute a copy so kernel timestamps and rendered PNG bytes stay untracked."""
    execution_dir.mkdir(parents=True, exist_ok=True)
    output_stem = f"{notebook_path.stem}.executed"
    executed_path = execution_dir / f"{output_stem}.ipynb"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            "--execute",
            "--to",
            "notebook",
            "--output",
            output_stem,
            "--output-dir",
            str(execution_dir),
            str(notebook_path),
        ],
        check=True,
        cwd=project_root,
    )
    executed = nbf.read(executed_path, as_version=4)
    code_cells = [cell for cell in executed.cells if cell.cell_type == "code"]
    if not code_cells or any(cell.execution_count is None or not cell.outputs for cell in code_cells):
        raise RuntimeError("Notebook execution did not produce outputs for every code cell")
    return executed_path


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    source_path = project_root / "notebooks" / "fleet_utilization_analysis.ipynb"
    write_notebook(project_root / "outputs" / "analysis_summary.json", source_path)
    execute_notebook(source_path, project_root / "work", project_root)
