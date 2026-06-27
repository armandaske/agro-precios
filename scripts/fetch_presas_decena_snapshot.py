from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from src.extract.presas_agricolas import run_from_config

DEFAULT_OUTPUT_ROOT = Path("data/raw/presas_agricolas/decena")


@dataclass(frozen=True)
class TargetPeriod:
    year: int
    month: int
    day_block: int


def decena_from_day(day: int) -> int:
    if day < 1 or day > 31:
        raise ValueError(f"Dia invalido para decena: {day}")
    if day <= 10:
        return 1
    if day <= 20:
        return 2
    return 3


def target_period_from_date(target_date: date) -> TargetPeriod:
    return TargetPeriod(
        year=target_date.year,
        month=target_date.month,
        day_block=decena_from_day(target_date.day),
    )


def resolve_target_period(
    *,
    target_date: date | None,
    year: int | None,
    month: int | None,
    day_block: int | None,
) -> TargetPeriod:
    explicit_values = [year, month, day_block]
    if any(value is not None for value in explicit_values):
        if not all(value is not None for value in explicit_values):
            raise ValueError("Si usas anio/mes/decena, debes proporcionar los tres valores.")
        if target_date is not None:
            raise ValueError("Usa --target-date o --year/--month/--decena, no ambos.")
        if month < 1 or month > 12:
            raise ValueError(f"Mes invalido: {month}")
        if day_block not in {1, 2, 3}:
            raise ValueError(f"Decena invalida: {day_block}")
        return TargetPeriod(year=year, month=month, day_block=day_block)

    if target_date is None:
        target_date = datetime.now().date()
    return target_period_from_date(target_date)


def build_config_frame(period: TargetPeriod, query_name: str = "corte_nacional_decena") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "activo": True,
                "nombre_consulta": query_name,
                "tipo_consulta": "presas_periodo",
                "id_conagua": "",
                "anio": period.year,
                "mes": period.month,
                "decena": period.day_block,
                "anio_inicial": "",
                "anio_final": "",
                "nombre_oficial": "",
                "estado": "",
            }
        ]
    )


def run_directory(output_root: Path, period: TargetPeriod) -> Path:
    return output_root / f"{period.year:04d}" / f"{period.month:02d}"


def build_run_paths(
    *,
    output_root: Path,
    period: TargetPeriod,
    run_timestamp: datetime,
) -> dict[str, Path]:
    directory = run_directory(output_root, period)
    stamp = run_timestamp.strftime("%Y%m%d_%H%M%S")
    period_slug = f"{period.year:04d}_{period.month:02d}_d{period.day_block}"
    return {
        "directory": directory,
        "workbook": directory / f"presas_decena_{period_slug}_{stamp}.xlsx",
        "config": directory / f"presas_decena_config_{period_slug}_{stamp}.xlsx",
        "summary": directory / f"presas_decena_resumen_{period_slug}_{stamp}.json",
    }


def find_existing_period_workbooks(output_root: Path, period: TargetPeriod) -> list[Path]:
    directory = run_directory(output_root, period)
    if not directory.exists():
        return []
    pattern = f"presas_decena_{period.year:04d}_{period.month:02d}_d{period.day_block}_*.xlsx"
    return sorted(path for path in directory.glob(pattern) if path.is_file())


def write_config_workbook(config_path: Path, config_frame: pd.DataFrame) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(config_path, engine="openpyxl") as writer:
        config_frame.to_excel(writer, sheet_name="consultas", index=False)


def summarize_output_workbook(output_path: Path) -> dict[str, int]:
    snapshots = pd.read_excel(output_path, sheet_name="presas_periodo")
    errors = pd.read_excel(output_path, sheet_name="errores")
    return {
        "snapshot_rows": int(len(snapshots)),
        "error_rows": int(len(errors)),
    }


def write_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_run_status(*, row_count: int, error_count: int) -> str:
    if error_count > 0 and row_count > 0:
        return "partial_error"
    if error_count > 0:
        return "error"
    return "success"


def execute_snapshot_run(
    *,
    output_root: Path,
    period: TargetPeriod,
    force: bool = False,
    run_timestamp: datetime | None = None,
) -> dict[str, Any]:
    run_timestamp = run_timestamp or datetime.now()
    existing = find_existing_period_workbooks(output_root, period)
    paths = build_run_paths(output_root=output_root, period=period, run_timestamp=run_timestamp)

    if existing and not force:
        summary = {
            "status": "skipped_existing",
            "run_timestamp": run_timestamp.isoformat(),
            "target_year": period.year,
            "target_month": period.month,
            "target_decena": period.day_block,
            "output_path": None,
            "config_path": None,
            "existing_output_paths": [str(path.resolve()) for path in existing],
            "row_count": 0,
            "error_count": 0,
        }
        write_summary(paths["summary"], summary)
        return summary

    config_frame = build_config_frame(period)
    write_config_workbook(paths["config"], config_frame)

    try:
        output_path = run_from_config(paths["config"], output_path=paths["workbook"])
        counts = summarize_output_workbook(output_path)
        status = build_run_status(
            row_count=counts["snapshot_rows"],
            error_count=counts["error_rows"],
        )
        summary = {
            "status": status,
            "run_timestamp": run_timestamp.isoformat(),
            "target_year": period.year,
            "target_month": period.month,
            "target_decena": period.day_block,
            "output_path": str(output_path.resolve()),
            "config_path": str(paths["config"].resolve()),
            "existing_output_paths": [str(path.resolve()) for path in existing],
            "row_count": counts["snapshot_rows"],
            "error_count": counts["error_rows"],
        }
    except Exception as exc:
        summary = {
            "status": "error",
            "run_timestamp": run_timestamp.isoformat(),
            "target_year": period.year,
            "target_month": period.month,
            "target_decena": period.day_block,
            "output_path": str(paths["workbook"].resolve()),
            "config_path": str(paths["config"].resolve()),
            "existing_output_paths": [str(path.resolve()) for path in existing],
            "row_count": 0,
            "error_count": 1,
            "error": str(exc),
        }
        write_summary(paths["summary"], summary)
        raise

    write_summary(paths["summary"], summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga el corte nacional de Presas Agricolas para una decena y lo guarda con trazabilidad."
    )
    parser.add_argument(
        "--target-date",
        type=date.fromisoformat,
        help="Fecha base YYYY-MM-DD para resolver la decena a consultar.",
    )
    parser.add_argument("--year", type=int, help="Anio explicito del corte.")
    parser.add_argument("--month", type=int, help="Mes explicito del corte.")
    parser.add_argument("--decena", type=int, help="Decena explicita del corte: 1, 2 o 3.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Directorio raiz de salida. Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite volver a descargar una decena aunque ya exista un archivo previo para ese periodo.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    period = resolve_target_period(
        target_date=args.target_date,
        year=args.year,
        month=args.month,
        day_block=args.decena,
    )
    summary = execute_snapshot_run(
        output_root=args.output_root,
        period=period,
        force=args.force,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] not in {"success", "skipped_existing"}:
        sys.exit(1)


if __name__ == "__main__":
    main()
