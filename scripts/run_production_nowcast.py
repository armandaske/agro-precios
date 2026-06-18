from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.production_nowcast import run_production_nowcast_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera el nowcast de produccion y rendimiento agricola.")
    parser.add_argument("--avance-root", type=Path, default=Path("data/raw/avance_agricola_batch"))
    parser.add_argument("--cierre-root", type=Path, default=Path("data/raw/cierre_agricola_batch"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis/production_nowcast"))
    parser.add_argument("--water-features", type=Path)
    parser.add_argument("--force-model", choices=["xgboost", "base_historica"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_production_nowcast_pipeline(
        args.avance_root,
        args.cierre_root,
        args.output_dir,
        water_path=args.water_features,
        force_model=args.force_model,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
