"""One-command reproducible pipeline for the complete portfolio case."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from src.analyze import run_analysis
from src.build_marts import build_marts
from src.build_portable_artifacts import build_artifacts
from src.create_notebook import execute_notebook, write_notebook
from src.generate_data import run_generator
from src.render_case_report import render_report


def run_pipeline(root: Path, hours: int, cars: int, skip_notebook: bool) -> None:
    raw_dir = root / "data" / "raw"
    processed_dir = root / "data" / "processed"
    outputs_dir = root / "outputs"
    run_generator(raw_dir, datetime(2025, 1, 1), hours, cars, seed=20260812)
    build_marts(raw_dir, processed_dir, root / "sql")
    run_analysis(processed_dir, raw_dir, outputs_dir)
    render_report(outputs_dir, root / "docs")
    build_artifacts(root)
    notebook_path = root / "notebooks" / "fleet_utilization_analysis.ipynb"
    write_notebook(outputs_dir / "analysis_summary.json", notebook_path)
    if not skip_notebook:
        execute_notebook(notebook_path, root / "work", root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate, model, analyse and document the case.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--hours", type=int, default=24 * 365)
    parser.add_argument("--cars", type=int, default=156)
    parser.add_argument("--skip-notebook", action="store_true")
    args = parser.parse_args()
    run_pipeline(args.root.resolve(), args.hours, args.cars, args.skip_notebook)


if __name__ == "__main__":
    main()
