from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Allow execution both as `python scripts/fetch_avance_batch.py`
# and `python -m scripts.fetch_avance_batch`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extract.avance_agricola_requests import build_report, configure_logging

LOGGER = logging.getLogger("fetch_avance_batch")

PRODUCT_SHEET_NAME = "productos"
DEFAULT_OUTPUT_ROOT = Path("data/raw/avance_agricola_batch")
DEFAULT_SUMMARY_NAME = "batch_summary.json"
REQUIRED_COLUMNS = ("activo", "producto_canonico", "avance_agricola_habilitado", "cultivo_avance_agricola")


@dataclass
class AvanceBatchItem:
    canonical_product: str
    avance_crop_name: str


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.casefold().split())


def _slugify(value: str) -> str:
    return _normalize_key(value).replace(" ", "_")


def _build_run_dir(output_root: Path, year: int, month: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_root / f"run_{timestamp}_{year}_{_slugify(month)}"


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


def load_batch_items(config_path: Path) -> list[AvanceBatchItem]:
    df = pd.read_excel(config_path, sheet_name=PRODUCT_SHEET_NAME, engine="openpyxl")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in '{PRODUCT_SHEET_NAME}': {', '.join(missing)}")

    items: list[AvanceBatchItem] = []
    for _, row in df.iterrows():
        if not _parse_bool(row["activo"]):
            continue
        if not _parse_bool(row["avance_agricola_habilitado"]):
            continue

        canonical_product = _clean_string(row["producto_canonico"])
        avance_crop_name = _clean_string(row["cultivo_avance_agricola"])
        if not canonical_product or not avance_crop_name:
            continue

        items.append(
            AvanceBatchItem(
                canonical_product=canonical_product,
                avance_crop_name=avance_crop_name,
            )
        )

    return items


def fetch_avance_batch(
    *,
    config_path: Path,
    output_root: Path,
    year: int,
    month: str,
    output_format: str,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = _build_run_dir(output_root, year, month)
    run_dir.mkdir(parents=True, exist_ok=True)
    items = load_batch_items(config_path)
    summary_rows: list[dict[str, Any]] = []

    for item in items:
        output_path = run_dir / f"{_slugify(item.canonical_product)}_{year}_{_slugify(month)}"
        record = {
            "canonical_product": item.canonical_product,
            "avance_crop_name": item.avance_crop_name,
            "year": year,
            "month": month,
            "output_path": str(output_path.with_suffix(f".{output_format}")),
            "status": "success",
            "error": "",
        }
        try:
            LOGGER.info(
                "Fetching Avance Agricola for canonical_product=%s crop=%s year=%s month=%s",
                item.canonical_product,
                item.avance_crop_name,
                year,
                month,
            )
            build_report(
                year=str(year),
                month=month,
                crop=item.avance_crop_name,
                output=output_path,
                output_format=output_format,
                debug=False,
                debug_dir=None,
            )
        except Exception as exc:  # noqa: BLE001
            record["status"] = "failed"
            record["error"] = str(exc)
            LOGGER.error(
                "Failed Avance Agricola fetch for canonical_product=%s crop=%s year=%s month=%s: %s",
                item.canonical_product,
                item.avance_crop_name,
                year,
                month,
                exc,
            )
        summary_rows.append(record)

    summary = {
        "config_path": str(config_path),
        "output_root": str(output_root),
        "run_dir": str(run_dir),
        "year": year,
        "month": month,
        "requested_products": len(items),
        "requested_jobs": len(summary_rows),
        "succeeded_jobs": sum(1 for row in summary_rows if row["status"] == "success"),
        "failed_jobs": sum(1 for row in summary_rows if row["status"] == "failed"),
        "jobs": summary_rows,
    }
    summary_path = run_dir / DEFAULT_SUMMARY_NAME
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch normalized Avance Agricola exports for the configured canonical products."
    )
    parser.add_argument("--config", default=Path("config/products.xlsx"), type=Path, help="Path to products.xlsx")
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        type=Path,
        help="Directory where normalized Avance exports will be written",
    )
    parser.add_argument("--year", required=True, type=int, help="Year to fetch, for example 2026")
    parser.add_argument(
        "--month",
        required=True,
        help="Visible month label or combo value, for example Febrero or 2",
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
        summary = fetch_avance_batch(
            config_path=args.config,
            output_root=args.output_root,
            year=args.year,
            month=args.month,
            output_format=args.output_format,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Batch fetch failed before completion: %s", exc)
        return 1

    LOGGER.info(
        "Avance batch finished: %s succeeded, %s failed. Summary: %s",
        summary["succeeded_jobs"],
        summary["failed_jobs"],
        summary["summary_path"],
    )
    return 0 if summary["succeeded_jobs"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
