from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.water_risk import run_water_risk_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entrena y ejecuta el monitor predictivo de riesgo hidrico.")
    parser.add_argument("--input-root", type=Path, default=Path("data/raw/presas_agricolas"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis/water_risk"))
    parser.add_argument("--climate-file", type=Path)
    parser.add_argument("--horizons", type=int, nargs="+", default=[3, 6, 9])
    parser.add_argument("--thresholds", type=float, nargs="+", default=[40, 25, 15])
    parser.add_argument(
        "--force-model",
        choices=[
            "xgboost_nivel",
            "xgboost_delta",
            "decena_anterior",
            "misma_decena_anio_anterior",
            "promedio_3_decenas",
            "delta_estacional_mediana",
        ],
        help="Fuerza el metodo operativo para demo. Si se omite, se elige por mejor MAE fuera de muestra.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_water_risk_pipeline(
        args.input_root,
        args.output_dir,
        climate_path=args.climate_file,
        horizons=tuple(args.horizons),
        thresholds=tuple(args.thresholds),
        force_model=args.force_model,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
