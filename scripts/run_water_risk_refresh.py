from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from scripts.fetch_presas_decena_snapshot import (
    execute_snapshot_run,
    resolve_target_period,
)
from src.analysis.public_data import fetch_nasa_power_weather
from src.analysis.water_risk import run_water_risk_pipeline


def atomic_publish_html(source_path: Path, target_path: Path) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"No existe el HTML origen para publicar: {source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(target_path.name + ".tmp")
    shutil.copy2(source_path, temp_path)
    temp_path.replace(target_path)
    return target_path


def write_refresh_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresca el monitor de riesgo hidrico de forma idempotente para scheduler."
    )
    parser.add_argument(
        "--publish-html-to",
        type=Path,
        required=True,
        help="Ruta absoluta del HTML canonico servido al usuario final.",
    )
    parser.add_argument("--presas-root", type=Path, default=Path("data/raw/presas_agricolas"))
    parser.add_argument(
        "--decena-output-root",
        type=Path,
        help="Raiz donde el wrapper de decena guarda snapshots. Default: <presas-root>/decena",
    )
    parser.add_argument("--water-output-dir", type=Path, default=Path("data/analysis/water_risk"))
    parser.add_argument(
        "--climate-output",
        type=Path,
        default=Path("data/raw/climate/nasa_power_decena.parquet"),
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        help="JSON resumen de la corrida. Default: <water-output-dir>/water_risk_refresh_summary.json",
    )
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--decena", type=int)
    parser.add_argument(
        "--force-decena-fetch",
        action="store_true",
        help="Permite redescargar una decena aunque ya exista en disco.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=40,
        help="Dias de superposicion al actualizar el parquet climatico incremental.",
    )
    parser.add_argument("--climate-state")
    parser.add_argument("--climate-limit", type=int)
    parser.add_argument("--climate-pause-seconds", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.publish_html_to.is_absolute():
        raise ValueError("--publish-html-to debe ser una ruta absoluta.")

    decena_output_root = args.decena_output_root or (args.presas_root / "decena")
    summary_path = args.summary_path or (args.water_output_dir / "water_risk_refresh_summary.json")
    run_started_at = datetime.now()
    summary: dict[str, Any] = {
        "status": "error",
        "started_at": run_started_at.isoformat(timespec="seconds"),
        "finished_at": None,
        "decena_status": "not_run",
        "climate_status": "not_run",
        "model_status": "not_run",
        "publish_status": "not_run",
        "snapshot_path": None,
        "climate_path": str(args.climate_output.resolve()),
        "analysis_html_path": str((args.water_output_dir / "monitoreo_riesgo_hidrico.html").resolve()),
        "published_html_path": str(args.publish_html_to.resolve()),
        "used_existing_climate_fallback": False,
        "target_period": None,
    }

    try:
        period = resolve_target_period(
            target_date=args.target_date,
            year=args.year,
            month=args.month,
            day_block=args.decena,
        )
        summary["target_period"] = {
            "year": period.year,
            "month": period.month,
            "decena": period.day_block,
        }

        decena_summary = execute_snapshot_run(
            output_root=decena_output_root,
            period=period,
            force=args.force_decena_fetch,
        )
        summary["decena_status"] = decena_summary["status"]
        summary["snapshot_path"] = decena_summary.get("output_path")

        if decena_summary["status"] == "skipped_existing":
            summary["status"] = "skipped_existing"
            summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
            write_refresh_summary(summary_path, summary)
            return 0

        if decena_summary["status"] != "success":
            raise RuntimeError(
                f"El wrapper de presas no quedo en success: {decena_summary['status']}"
            )

        climate_path_to_use = args.climate_output
        climate_end_date = run_started_at.date().isoformat()
        try:
            fetch_nasa_power_weather(
                args.presas_root,
                args.climate_output,
                start_date=None,
                end_date=climate_end_date,
                state=args.climate_state,
                limit=args.climate_limit,
                pause_seconds=args.climate_pause_seconds,
                merge_existing=True,
                lookback_days=args.lookback_days,
            )
            summary["climate_status"] = "updated"
        except Exception as exc:  # noqa: BLE001
            if args.climate_output.exists():
                summary["climate_status"] = "stale_fallback"
                summary["used_existing_climate_fallback"] = True
                summary["climate_error"] = str(exc)
                climate_path_to_use = args.climate_output
            else:
                raise RuntimeError(f"Fallo la actualizacion climatica sin fallback disponible: {exc}") from exc

        run_water_risk_pipeline(
            args.presas_root,
            args.water_output_dir,
            climate_path=climate_path_to_use,
        )
        summary["model_status"] = "updated"

        analysis_html_path = args.water_output_dir / "monitoreo_riesgo_hidrico.html"
        published = atomic_publish_html(analysis_html_path, args.publish_html_to)
        summary["publish_status"] = "updated"
        summary["analysis_html_path"] = str(analysis_html_path.resolve())
        summary["published_html_path"] = str(published.resolve())
        summary["status"] = "updated"
        summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
        write_refresh_summary(summary_path, summary)
        return 0
    except Exception as exc:  # noqa: BLE001
        summary["error"] = str(exc)
        summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
        write_refresh_summary(summary_path, summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
