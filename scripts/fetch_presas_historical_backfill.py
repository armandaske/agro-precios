from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.extract.presas_agricolas import fetch_available_years, fetch_default_period, run_from_config

DEFAULT_OUTPUT_ROOT = Path("data/raw/presas_agricolas/backfill")


def build_config_frame(*, year: int, latest_period: dict[str, int]) -> pd.DataFrame:
    month = 1
    day_block = 1
    if year == latest_period["year"]:
        month = 1
        day_block = 1
    return pd.DataFrame(
        [
            {
                "activo": True,
                "nombre_consulta": f"corte_nacional_{year}",
                "tipo_consulta": "presas_periodo",
                "id_conagua": "",
                "anio": year,
                "mes": month,
                "decena": day_block,
                "anio_inicial": "",
                "anio_final": year,
                "nombre_oficial": "",
                "estado": "",
            }
        ]
    )


def summarize_workbook(path: Path) -> dict[str, int]:
    snapshots = pd.read_excel(path, sheet_name="presas_periodo")
    errors = pd.read_excel(path, sheet_name="errores")
    return {
        "snapshot_rows": int(len(snapshots)),
        "snapshot_dams": int(snapshots["id_conagua"].nunique()) if not snapshots.empty else 0,
        "error_rows": int(len(errors)),
    }


def run_year_backfill(
    *,
    year: int,
    output_root: Path,
    configs_root: Path,
    latest_period: dict[str, int],
    force: bool,
) -> dict[str, object]:
    output_path = output_root / f"presas_agricolas_backfill_{year}.xlsx"
    config_path = configs_root / f"presas_agricolas_backfill_config_{year}.xlsx"
    if output_path.exists() and not force:
        counts = summarize_workbook(output_path)
        return {
            "year": year,
            "status": "skipped_existing",
            "output_path": str(output_path.resolve()),
            **counts,
        }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_frame = build_config_frame(year=year, latest_period=latest_period)
    with pd.ExcelWriter(config_path, engine="openpyxl") as writer:
        config_frame.to_excel(writer, sheet_name="consultas", index=False)

    result_path = run_from_config(config_path, output_path=output_path)
    counts = summarize_workbook(result_path)
    return {
        "year": year,
        "status": "success" if counts["error_rows"] == 0 else "partial_with_errors",
        "output_path": str(result_path.resolve()),
        **counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill anual de cortes nacionales de presas usando el extractor existente."
    )
    parser.add_argument("--start-year", type=int, default=1999)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Vuelve a descargar aunque ya exista el workbook anual.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    available_years = sorted(fetch_available_years())
    latest_period = fetch_default_period()
    end_year = args.end_year or latest_period["year"]
    selected_years = [year for year in available_years if args.start_year <= year <= end_year]
    if not selected_years:
        raise ValueError(
            f"No hay anios disponibles entre {args.start_year} y {end_year}. "
            f"Portal: {min(available_years)}-{max(available_years)}."
        )

    output_root = args.output_root
    configs_root = output_root / "configs"
    output_root.mkdir(parents=True, exist_ok=True)

    run_results = []
    for year in selected_years:
        result = run_year_backfill(
            year=year,
            output_root=output_root,
            configs_root=configs_root,
            latest_period=latest_period,
            force=args.force,
        )
        run_results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start_year": args.start_year,
        "end_year": end_year,
        "years_requested": selected_years,
        "years_completed": [item["year"] for item in run_results if item["status"] != "skipped_existing"],
        "results": run_results,
    }
    summary_path = output_root / "backfill_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
