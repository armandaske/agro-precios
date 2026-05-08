from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# Allow execution both as `python scripts/fetch_cierre_batch.py`
# and `python -m scripts.fetch_cierre_batch`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extract.cierre_agricola_requests import build_report, configure_logging

LOGGER = logging.getLogger("fetch_cierre_batch")

PRODUCT_SHEET_NAME = "productos"
DEFAULT_YEARS = (2023, 2024)
DEFAULT_OUTPUT_ROOT = Path("data/raw/cierre_agricola_batch")
DEFAULT_SUMMARY_NAME = "batch_summary.json"
REQUIRED_COLUMNS = ("activo", "producto_canonico", "cultivo_cierre_agricola")

# These overrides exist because the current config workbook only fills
# `cultivo_cierre_agricola` for Aguacate, but the user wants all 10 products now.
DEFAULT_CIERRE_CROP_OVERRIDES = {
    "aguacate": "Aguacate",
    "tomate rojo": "Tomate rojo (jitomate)",
    "elote": "Elote",
    "zanahoria": "Zanahoria",
    "cebolla": "Cebolla",
    "chile verde": "Chile verde",
    "limon": "Limón",
    "platano": "Plátano",
    "mango": "Mango",
    "papa": "Papa",
}


@dataclass
class CierreBatchItem:
    canonical_product: str
    cierre_crop_name: str


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.casefold().split())


def _slugify(value: str) -> str:
    return _normalize_key(value).replace(" ", "_")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí", "x"}


def _clean_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def load_batch_items(config_path: Path) -> list[CierreBatchItem]:
    df = pd.read_excel(config_path, sheet_name=PRODUCT_SHEET_NAME, engine="openpyxl")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in '{PRODUCT_SHEET_NAME}': {', '.join(missing)}")

    items: list[CierreBatchItem] = []
    for _, row in df.iterrows():
        if not _parse_bool(row["activo"]):
            continue

        canonical_product = _clean_string(row["producto_canonico"])
        if not canonical_product:
            continue

        configured_crop = _clean_string(row["cultivo_cierre_agricola"])
        if configured_crop:
            cierre_crop_name = configured_crop
        else:
            fallback = DEFAULT_CIERRE_CROP_OVERRIDES.get(_normalize_key(canonical_product))
            if not fallback:
                raise ValueError(
                    f"No Cierre crop mapping found for canonical product '{canonical_product}'. "
                    "Fill 'cultivo_cierre_agricola' in config/products.xlsx or extend the fallback map."
                )
            cierre_crop_name = fallback

        items.append(CierreBatchItem(canonical_product=canonical_product, cierre_crop_name=cierre_crop_name))

    return items


def fetch_cierre_batch(
    *,
    config_path: Path,
    output_root: Path,
    years: list[int],
    output_format: str,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    items = load_batch_items(config_path)
    summary_rows: list[dict[str, Any]] = []

    for item in items:
        for year in years:
            output_path = output_root / f"{_slugify(item.canonical_product)}_{year}"
            record = {
                "canonical_product": item.canonical_product,
                "cierre_crop_name": item.cierre_crop_name,
                "year": year,
                "output_path": str(output_path.with_suffix(f'.{output_format}')),
                "status": "success",
                "error": "",
            }
            try:
                LOGGER.info(
                    "Fetching Cierre Agricola for canonical_product=%s crop=%s year=%s",
                    item.canonical_product,
                    item.cierre_crop_name,
                    year,
                )
                build_report(
                    year=str(year),
                    crop=item.cierre_crop_name,
                    output=output_path,
                    output_format=output_format,
                    debug=False,
                    debug_dir=None,
                )
            except Exception as exc:  # noqa: BLE001
                record["status"] = "failed"
                record["error"] = str(exc)
                LOGGER.error(
                    "Failed Cierre Agricola fetch for canonical_product=%s crop=%s year=%s: %s",
                    item.canonical_product,
                    item.cierre_crop_name,
                    year,
                    exc,
                )
            summary_rows.append(record)

    summary = {
        "config_path": str(config_path),
        "output_root": str(output_root),
        "years": years,
        "requested_products": len(items),
        "requested_jobs": len(summary_rows),
        "succeeded_jobs": sum(1 for row in summary_rows if row["status"] == "success"),
        "failed_jobs": sum(1 for row in summary_rows if row["status"] == "failed"),
        "jobs": summary_rows,
    }
    summary_path = output_root / DEFAULT_SUMMARY_NAME
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch normalized Cierre Agricola exports for the configured canonical products."
    )
    parser.add_argument("--config", default=Path("config/products.xlsx"), type=Path, help="Path to products.xlsx")
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        type=Path,
        help="Directory where normalized Cierre exports will be written",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=list(DEFAULT_YEARS),
        help="Years to fetch, e.g. --years 2023 2024",
    )
    parser.add_argument(
        "--output-format",
        choices=("xls", "csv", "xlsx"),
        default="xlsx",
        help="Output format for the normalized exports",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(False)

    try:
        summary = fetch_cierre_batch(
            config_path=args.config,
            output_root=args.output_root,
            years=args.years,
            output_format=args.output_format,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Batch fetch failed before completion: %s", exc)
        return 1

    LOGGER.info(
        "Cierre batch finished: %s succeeded, %s failed. Summary: %s",
        summary["succeeded_jobs"],
        summary["failed_jobs"],
        summary["summary_path"],
    )
    return 0 if summary["succeeded_jobs"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
