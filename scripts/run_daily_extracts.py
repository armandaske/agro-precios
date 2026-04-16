from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Allow execution both as `python scripts/run_daily_extracts.py` and `python -m scripts.run_daily_extracts`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extract.cierre_agricola_requests import fetch_report_dataframe
from src.extract.spreadsheet_localization import (
    CONFIG_COLUMN_ALIASES,
    DAILY_FAILURE_COLUMN_MAP,
    DAILY_META_COLUMN_MAP,
    DAILY_SHEET_NAMES,
    DAILY_SOURCE_COLUMN_MAPS,
    PRODUCT_SHEET_NAME,
    PRODUCT_SHEET_NAME_ALIASES,
    rename_columns,
    rename_mapping_keys,
)
from src.extract.sniim import fetch_sniim_fruits_vegetables
from src.extract.walmart_produce_scraper import choose_best_records, collect_search_records


LOGGER = logging.getLogger("daily_extracts")

REQUIRED_COLUMNS = [
    "active",
    "canonical_product",
    "walmart_enabled",
    "walmart_search_terms",
    "sniim_enabled",
    "sniim_producto_id",
    "sniim_origen_id",
    "sniim_destino_id",
    "sniim_precios_por_id",
    "cierre_enabled",
    "cierre_crop_name",
]
FAILURE_COLUMNS = [
    "row_number",
    "canonical_product",
    "source_name",
    "identifier",
    "error",
]
DEFAULT_DATA_COLUMNS = {
    "walmart": ["run_date", "canonical_product", "source_name", "search_terms_used"],
    "sniim": ["run_date", "canonical_product", "source_name", "query_start_date", "query_end_date"],
    "cierre_agricola": ["run_date", "canonical_product", "source_name", "query_year", "cierre_crop_name"],
}


@dataclass
class ProductConfig:
    row_number: int
    canonical_product: str
    walmart_enabled: bool
    walmart_search_terms: list[str]
    sniim_enabled: bool
    sniim_producto_id: int | None
    sniim_origen_id: int
    sniim_destino_id: int
    sniim_precios_por_id: int
    cierre_enabled: bool
    cierre_crop_name: str


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "t", "yes", "y", "si", "sí", "x"}


def _parse_optional_int(value: Any, default: int | None = None) -> int | None:
    if pd.isna(value) or str(value).strip() == "":
        return default

    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value).strip())


def _value_or_default(value: int | None, default: int) -> int:
    return default if value is None else value


def _clean_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _parse_walmart_terms(raw_value: Any, canonical_product: str) -> list[str]:
    raw_text = _clean_string(raw_value)
    if not raw_text:
        return [canonical_product] if canonical_product else []
    return [term.strip() for term in raw_text.split("|") if term.strip()]


def parse_run_date(raw_value: str | None) -> date:
    if raw_value:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    return datetime.now().date()


def _read_products_sheet(config_path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for sheet_name in PRODUCT_SHEET_NAME_ALIASES:
        try:
            return pd.read_excel(config_path, sheet_name=sheet_name, engine="openpyxl")
        except ValueError as exc:
            last_error = exc

    available_sheets = pd.ExcelFile(config_path, engine="openpyxl").sheet_names
    available = ", ".join(available_sheets)
    raise ValueError(
        f"No se encontrÃ³ la hoja de configuraciÃ³n '{PRODUCT_SHEET_NAME}'. Hojas disponibles: {available}"
    ) from last_error


def load_products_config(config_path: Path) -> list[ProductConfig]:
    df = _read_products_sheet(config_path)
    df = df.rename(columns=lambda column: CONFIG_COLUMN_ALIASES.get(str(column), str(column)))
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in '{PRODUCT_SHEET_NAME}': {', '.join(missing_columns)}")

    df = df[REQUIRED_COLUMNS].dropna(how="all")
    configs: list[ProductConfig] = []

    for idx, row in df.iterrows():
        if not _parse_bool(row["active"]):
            continue

        canonical_product = _clean_string(row["canonical_product"])
        configs.append(
            ProductConfig(
                row_number=idx + 2,
                canonical_product=canonical_product,
                walmart_enabled=_parse_bool(row["walmart_enabled"]),
                walmart_search_terms=_parse_walmart_terms(row["walmart_search_terms"], canonical_product),
                sniim_enabled=_parse_bool(row["sniim_enabled"]),
                sniim_producto_id=_parse_optional_int(row["sniim_producto_id"]),
                sniim_origen_id=_value_or_default(_parse_optional_int(row["sniim_origen_id"], -1), -1),
                sniim_destino_id=_value_or_default(_parse_optional_int(row["sniim_destino_id"], -1), -1),
                sniim_precios_por_id=_value_or_default(_parse_optional_int(row["sniim_precios_por_id"], 2), 2),
                cierre_enabled=_parse_bool(row["cierre_enabled"]),
                cierre_crop_name=_clean_string(row["cierre_crop_name"]),
            )
        )

    return configs


def _failure_record(
    config: ProductConfig,
    source_name: str,
    error: str,
    *,
    identifier: str = "",
) -> dict[str, Any]:
    return {
        "row_number": config.row_number,
        "canonical_product": config.canonical_product,
        "source_name": source_name,
        "identifier": identifier,
        "error": error,
    }


def _concat_frames(frames: list[pd.DataFrame], default_columns: list[str]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=default_columns)
    return pd.concat(frames, ignore_index=True)


def _write_source_workbook(
    output_path: Path,
    data_df: pd.DataFrame,
    failures: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    source_name: str,
    default_columns: list[str],
) -> None:
    failures_df = rename_columns(pd.DataFrame(failures, columns=FAILURE_COLUMNS), DAILY_FAILURE_COLUMN_MAP)
    data_to_write = data_df if not data_df.empty else pd.DataFrame(columns=default_columns)
    localized_data_df = rename_columns(data_to_write, DAILY_SOURCE_COLUMN_MAPS[source_name])
    localized_meta_df = pd.DataFrame([rename_mapping_keys(meta, DAILY_META_COLUMN_MAP)])

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        localized_data_df.to_excel(writer, sheet_name=DAILY_SHEET_NAMES["data"], index=False)
        if not failures_df.empty:
            failures_df.to_excel(writer, sheet_name=DAILY_SHEET_NAMES["failures"], index=False)
        localized_meta_df.to_excel(writer, sheet_name=DAILY_SHEET_NAMES["meta"], index=False)


def run_walmart(configs: list[ProductConfig], run_date: date, output_dir: Path, config_path: Path) -> dict[str, Any]:
    source_name = "walmart"
    source_configs = [config for config in configs if config.walmart_enabled]
    failures: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []

    for config in source_configs:
        if not config.canonical_product:
            failures.append(_failure_record(config, source_name, "canonical_product is required"))
            continue
        if not config.walmart_search_terms:
            failures.append(_failure_record(config, source_name, "No Walmart search terms configured"))
            continue

        try:
            search_map = {config.canonical_product: config.walmart_search_terms}
            records = collect_search_records(search_terms=search_map)
            best_records = choose_best_records(records, [config.canonical_product], search_map)
            if not best_records:
                raise ValueError("No Walmart records found for configured terms")

            frame = pd.DataFrame(best_records)
            frame["run_date"] = run_date.isoformat()
            frame["canonical_product"] = config.canonical_product
            frame["source_name"] = source_name
            frame["search_terms_used"] = " | ".join(config.walmart_search_terms)
            frames.append(frame)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                _failure_record(
                    config,
                    source_name,
                    str(exc),
                    identifier=" | ".join(config.walmart_search_terms),
                )
            )

    data_df = _concat_frames(frames, DEFAULT_DATA_COLUMNS[source_name])
    output_path = output_dir / f"{source_name}_{run_date.isoformat()}.xlsx"
    if source_configs:
        _write_source_workbook(
            output_path,
            data_df,
            failures,
            {
                "source_name": source_name,
                "run_date": run_date.isoformat(),
                "config_path": str(config_path),
                "rows_attempted": len(source_configs),
                "rows_succeeded": len(frames),
                "rows_failed": len(failures),
            },
            source_name=source_name,
            default_columns=DEFAULT_DATA_COLUMNS[source_name],
        )

    return {
        "source_name": source_name,
        "attempted": len(source_configs),
        "succeeded": len(frames),
        "failed": len(failures),
        "status": _source_status(len(source_configs), len(frames), len(failures)),
        "output_path": str(output_path) if source_configs else None,
        "failures": failures,
        "records": int(len(data_df)),
    }


def run_sniim(configs: list[ProductConfig], run_date: date, output_dir: Path, config_path: Path) -> dict[str, Any]:
    source_name = "sniim"
    source_configs = [config for config in configs if config.sniim_enabled]
    failures: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    query_date = run_date - timedelta(days=1)
    query_date_str = query_date.isoformat()

    for config in source_configs:
        if not config.canonical_product:
            failures.append(_failure_record(config, source_name, "canonical_product is required"))
            continue
        if config.sniim_producto_id is None:
            failures.append(_failure_record(config, source_name, "sniim_producto_id is required"))
            continue

        try:
            frame = fetch_sniim_fruits_vegetables(
                fecha_inicio=query_date_str,
                fecha_final=query_date_str,
                producto_id=config.sniim_producto_id,
                origen_id=config.sniim_origen_id,
                destino_id=config.sniim_destino_id,
                precios_por_id=config.sniim_precios_por_id,
            ).copy()
            frame["run_date"] = run_date.isoformat()
            frame["canonical_product"] = config.canonical_product
            frame["source_name"] = source_name
            frame["query_start_date"] = query_date_str
            frame["query_end_date"] = query_date_str
            frames.append(frame)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                _failure_record(
                    config,
                    source_name,
                    str(exc),
                    identifier=str(config.sniim_producto_id),
                )
            )

    data_df = _concat_frames(frames, DEFAULT_DATA_COLUMNS[source_name])
    output_path = output_dir / f"{source_name}_{run_date.isoformat()}.xlsx"
    if source_configs:
        _write_source_workbook(
            output_path,
            data_df,
            failures,
            {
                "source_name": source_name,
                "run_date": run_date.isoformat(),
                "config_path": str(config_path),
                "rows_attempted": len(source_configs),
                "rows_succeeded": len(frames),
                "rows_failed": len(failures),
                "query_start_date": query_date_str,
                "query_end_date": query_date_str,
            },
            source_name=source_name,
            default_columns=DEFAULT_DATA_COLUMNS[source_name],
        )

    return {
        "source_name": source_name,
        "attempted": len(source_configs),
        "succeeded": len(frames),
        "failed": len(failures),
        "status": _source_status(len(source_configs), len(frames), len(failures)),
        "output_path": str(output_path) if source_configs else None,
        "failures": failures,
        "records": int(len(data_df)),
    }


def run_cierre_agricola(
    configs: list[ProductConfig],
    run_date: date,
    output_dir: Path,
    config_path: Path,
) -> dict[str, Any]:
    source_name = "cierre_agricola"
    source_configs = [config for config in configs if config.cierre_enabled]
    failures: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    query_year = str(run_date.year)

    for config in source_configs:
        if not config.canonical_product:
            failures.append(_failure_record(config, source_name, "canonical_product is required"))
            continue
        if not config.cierre_crop_name:
            failures.append(_failure_record(config, source_name, "cierre_crop_name is required"))
            continue

        try:
            frame = fetch_report_dataframe(year=query_year, crop=config.cierre_crop_name).copy()
            frame["run_date"] = run_date.isoformat()
            frame["canonical_product"] = config.canonical_product
            frame["source_name"] = source_name
            frame["cierre_crop_name"] = config.cierre_crop_name
            frame["query_year"] = int(query_year)
            frames.append(frame)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                _failure_record(
                    config,
                    source_name,
                    str(exc),
                    identifier=config.cierre_crop_name,
                )
            )

    data_df = _concat_frames(frames, DEFAULT_DATA_COLUMNS[source_name])
    output_path = output_dir / f"{source_name}_{run_date.isoformat()}.xlsx"
    if source_configs:
        _write_source_workbook(
            output_path,
            data_df,
            failures,
            {
                "source_name": source_name,
                "run_date": run_date.isoformat(),
                "config_path": str(config_path),
                "rows_attempted": len(source_configs),
                "rows_succeeded": len(frames),
                "rows_failed": len(failures),
                "query_year": int(query_year),
            },
            source_name=source_name,
            default_columns=DEFAULT_DATA_COLUMNS[source_name],
        )

    return {
        "source_name": source_name,
        "attempted": len(source_configs),
        "succeeded": len(frames),
        "failed": len(failures),
        "status": _source_status(len(source_configs), len(frames), len(failures)),
        "output_path": str(output_path) if source_configs else None,
        "failures": failures,
        "records": int(len(data_df)),
    }


def _source_status(attempted: int, succeeded: int, failed: int) -> str:
    if attempted == 0:
        return "skipped"
    if succeeded == attempted:
        return "success"
    if succeeded > 0 and failed > 0:
        return "partial"
    return "failed"


def orchestrate_daily_run(config_path: Path, output_root: Path, run_date: date) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config workbook not found: {config_path}")

    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / run_date.isoformat()
    run_dir.mkdir(parents=True, exist_ok=True)

    configs = load_products_config(config_path)
    shutil.copy2(config_path, run_dir / "products_snapshot.xlsx")

    source_results = [
        run_walmart(configs, run_date, run_dir, config_path),
        run_sniim(configs, run_date, run_dir, config_path),
        run_cierre_agricola(configs, run_date, run_dir, config_path),
    ]

    summary = {
        "run_date": run_date.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config_path": str(config_path),
        "run_directory": str(run_dir),
        "active_products": len(configs),
        "sources": {result["source_name"]: {k: v for k, v in result.items() if k != "failures"} for result in source_results},
        "failures": [failure for result in source_results for failure in result["failures"]],
    }

    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 3 daily extraction jobs and save consolidated XLSX outputs.")
    parser.add_argument("--config", required=True, type=Path, help="Path to the products workbook (.xlsx)")
    parser.add_argument("--output-root", required=True, type=Path, help="Root directory for dated run folders")
    parser.add_argument("--run-date", help="Override run date in YYYY-MM-DD format")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    Path("logs").mkdir(parents=True, exist_ok=True)

    try:
        run_date = parse_run_date(args.run_date)
        summary = orchestrate_daily_run(args.config, args.output_root, run_date)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Daily extraction run failed before completion: %s", exc)
        return 1

    success_sources = sum(1 for source in summary["sources"].values() if source["succeeded"] > 0)
    LOGGER.info("Daily extraction summary written to %s", summary["summary_path"])

    if success_sources == 0:
        LOGGER.error("Daily extraction run completed but no source produced successful results")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
