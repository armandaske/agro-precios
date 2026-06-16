from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from scripts.build_master_price_workbook import build_master_workbook
from src.analysis.price_shock import run_price_shock_pipeline
from src.analysis.production_nowcast import run_production_nowcast_pipeline
from src.analysis.water_risk import run_water_risk_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta los tres analisis predictivos en orden.")
    parser.add_argument("--daily-root", type=Path, default=Path("data/daily_runs"))
    parser.add_argument("--presas-root", type=Path, default=Path("data/raw/presas_agricolas"))
    parser.add_argument("--avance-root", type=Path, default=Path("data/raw/avance_agricola_batch"))
    parser.add_argument("--cierre-root", type=Path, default=Path("data/raw/cierre_agricola_batch"))
    parser.add_argument("--analysis-root", type=Path, default=Path("data/analysis"))
    parser.add_argument("--climate-file", type=Path)
    parser.add_argument("--international-features", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.analysis_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "generado_en": datetime.now().isoformat(timespec="seconds")
    }
    master_path = args.analysis_root / "master_price_workbook.xlsx"
    tables = build_master_workbook(
        args.daily_root,
        args.avance_root,
        master_path,
        args.cierre_root,
        args.international_features,
    )
    summary["workbook_maestro"] = {
        "ruta": str(master_path),
        "filas_comparacion": len(tables["compare_daily_wide"]),
    }
    water_dir = args.analysis_root / "water_risk"
    summary["riesgo_hidrico"] = run_water_risk_pipeline(
        args.presas_root,
        water_dir,
        climate_path=args.climate_file,
    )
    production_dir = args.analysis_root / "production_nowcast"
    summary["nowcast_produccion"] = run_production_nowcast_pipeline(
        args.avance_root,
        args.cierre_root,
        production_dir,
        water_path=water_dir / "state_decena_features.parquet",
    )
    price_dir = args.analysis_root / "price_shock"
    summary["alerta_precios"] = run_price_shock_pipeline(
        args.daily_root,
        price_dir,
        production_path=production_dir / "pronostico_produccion_mensual.csv",
        water_path=water_dir / "state_decena_features.parquet",
        international_features_path=args.international_features,
    )
    summary_path = args.analysis_root / "analysis_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
