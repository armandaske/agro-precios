from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extract.fred_public_csv import fetch_fred_dexmxus
from src.extract.world_bank_commodities import fetch_world_bank_pink_sheet


def fetch_public_international_prices(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "sin_tokens_api": True,
        "fuentes": {},
        "notas": [
            "USDA AMS se carga desde archivos publicos descargados manualmente en data/raw/international_prices/usda_ams/.",
            "IMF se carga desde archivos publicos descargados manualmente en data/raw/international_prices/imf/.",
        ],
    }
    for source_name, fetcher, source_dir in (
        ("world_bank", fetch_world_bank_pink_sheet, output_root / "world_bank"),
        ("fred", fetch_fred_dexmxus, output_root / "fred"),
    ):
        try:
            output_path = fetcher(source_dir)
            summary["fuentes"][source_name] = {
                "estado": "exitoso",
                "archivo": str(output_path),
            }
        except Exception as exc:  # noqa: BLE001
            summary["fuentes"][source_name] = {
                "estado": "error",
                "error": str(exc),
            }

    for directory in (output_root / "usda_ams", output_root / "imf"):
        directory.mkdir(parents=True, exist_ok=True)
        readme = directory / "README.txt"
        if not readme.exists():
            readme.write_text(
                "Coloca aqui archivos CSV/XLS/XLSX publicos descargados manualmente para normalizarlos sin API keys.\n",
                encoding="utf-8",
            )

    summary_path = output_root / "fetch_public_international_prices_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga precios internacionales publicos sin API keys.")
    parser.add_argument("--output-root", type=Path, default=Path("data/raw/international_prices"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = fetch_public_international_prices(args.output_root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
