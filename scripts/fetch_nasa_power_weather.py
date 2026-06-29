from __future__ import annotations

import argparse
from pathlib import Path

from src.analysis.public_data import fetch_nasa_power_weather


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga clima diario NASA POWER y lo agrega por decena.")
    parser.add_argument("--reservoir-root", type=Path, default=Path("data/raw/presas_agricolas"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/climate/nasa_power_decena.parquet"))
    parser.add_argument("--start-date")
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--state")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    parser.add_argument(
        "--merge-existing",
        action="store_true",
        help="Fusiona el nuevo rango con el parquet existente y conserva el historial previo.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=40,
        help="Dias de superposicion al refetch incremental cuando se usa --merge-existing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frame = fetch_nasa_power_weather(
        args.reservoir_root,
        args.output,
        start_date=args.start_date,
        end_date=args.end_date,
        state=args.state,
        limit=args.limit,
        pause_seconds=args.pause_seconds,
        merge_existing=args.merge_existing,
        lookback_days=args.lookback_days,
    )
    print(f"Filas: {len(frame)} | Presas: {frame['id_conagua'].nunique()} | Salida: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
