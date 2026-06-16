from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.price_shock import run_price_shock_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entrena y ejecuta la alerta temprana de precios.")
    parser.add_argument("--daily-root", type=Path, default=Path("data/daily_runs"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis/price_shock"))
    parser.add_argument("--production-forecast", type=Path)
    parser.add_argument("--water-features", type=Path)
    parser.add_argument("--international-features", type=Path)
    parser.add_argument("--horizons", type=int, nargs="+", default=[7, 14, 28])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_price_shock_pipeline(
        args.daily_root,
        args.output_dir,
        production_path=args.production_forecast,
        water_path=args.water_features,
        international_features_path=args.international_features,
        horizons=tuple(args.horizons),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
