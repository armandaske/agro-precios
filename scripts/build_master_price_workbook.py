from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd

# Allow execution both as `python scripts/build_master_price_workbook.py`
# and `python -m scripts.build_master_price_workbook`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_daily_extracts import load_products_config

LOGGER = logging.getLogger("build_master_price_workbook")

DATA_SHEET_ALIASES = ("datos", "data")
META_SHEET_ALIASES = ("metadatos", "meta")
FAILURE_SHEET_ALIASES = ("errores", "failures")
SNIIM_PANEL_UNIT_LABEL = "kg_calculado"
CIERRE_PANEL_PRICE_BASIS = "pmr_mxn_udm_weighted_by_produccion"
SNIIM_PANEL_PRICE_BASIS = "precio_frecuente_mean"
AVANCE_PANEL_PRICE_BASIS = "contexto_mensual_avance_agricola"

WALMART_READ_COLUMN_MAP = {
    "scraped_at_utc": "scraped_at_utc",
    "fecha_extraccion_utc": "scraped_at_utc",
    "source": "source",
    "fuente": "source",
    "source_page": "source_page",
    "pagina_fuente": "source_page",
    "source_query": "source_query",
    "termino_busqueda": "source_query",
    "product_raw": "product_raw",
    "producto_original": "product_raw",
    "product_canonical": "product_canonical",
    "producto_canonico": "product_canonical",
    "product_inferred": "product_inferred",
    "producto_inferido": "product_inferred",
    "price_mxn": "price_mxn",
    "precio_mxn": "price_mxn",
    "old_price_mxn": "old_price_mxn",
    "precio_anterior_mxn": "old_price_mxn",
    "promo_flag": "promo_flag",
    "esta_en_promocion": "promo_flag",
    "unit_raw": "unit_raw",
    "unidad_detectada": "unit_raw",
    "estimated_price_per_kg_mxn": "estimated_price_per_kg_mxn",
    "precio_estimado_por_kg_mxn": "estimated_price_per_kg_mxn",
    "presentation_weight_kg": "presentation_weight_kg",
    "peso_presentacion_kg": "presentation_weight_kg",
    "sales_unit_type": "sales_unit_type",
    "tipo_unidad_venta": "sales_unit_type",
    "average_weight_kg": "average_weight_kg",
    "peso_promedio_kg": "average_weight_kg",
    "brand_raw": "brand_raw",
    "marca_original": "brand_raw",
    "category_path": "category_path",
    "ruta_categoria": "category_path",
    "fresh_produce_flag": "fresh_produce_flag",
    "es_producto_fresco": "fresh_produce_flag",
    "run_date": "run_date",
    "fecha_corrida": "run_date",
    "canonical_product": "canonical_product",
    "producto_canonico.1": "canonical_product",
    "source_name": "source_name",
    "nombre_fuente": "source_name",
    "search_terms_used": "search_terms_used",
    "terminos_busqueda_utilizados": "search_terms_used",
}

CHEDRAUI_READ_COLUMN_MAP = dict(WALMART_READ_COLUMN_MAP)

SNIIM_READ_COLUMN_MAP = {
    "presentacion": "presentacion",
    "origen": "origen",
    "destino": "destino",
    "precio_frecuente": "precio_frecuente",
    "precio_minimo": "precio_minimo",
    "precio_maximo": "precio_maximo",
    "obs": "observaciones",
    "observaciones": "observaciones",
    "fecha_inicio_query": "fecha_inicio_query",
    "fecha_inicio_consulta": "fecha_inicio_query",
    "fecha_final_query": "fecha_final_query",
    "fecha_fin_consulta": "fecha_final_query",
    "producto_id": "producto_id",
    "id_producto": "producto_id",
    "producto_nombre_sitio": "producto_nombre_sitio",
    "producto_sniim": "producto_nombre_sitio",
    "origen_id": "origen_id",
    "id_origen": "origen_id",
    "destino_id": "destino_id",
    "id_destino": "destino_id",
    "origen_query": "origen_query",
    "origen_consulta": "origen_query",
    "destino_query": "destino_query",
    "destino_consulta": "destino_query",
    "precios_por_id": "precios_por_id",
    "id_precios_por": "precios_por_id",
    "registros_por_pagina": "registros_por_pagina",
    "fuente": "source_name_raw",
    "source_name_raw": "source_name_raw",
    "fecha_extraccion": "fecha_extraccion",
    "run_date": "run_date",
    "fecha_corrida": "run_date",
    "canonical_product": "canonical_product",
    "producto_canonico": "canonical_product",
    "source_name": "source_name",
    "nombre_fuente": "source_name",
    "query_start_date": "query_start_date",
    "fecha_inicio_consulta.1": "query_start_date",
    "query_end_date": "query_end_date",
    "fecha_fin_consulta.1": "query_end_date",
}

CIERRE_READ_COLUMN_MAP = {
    "numero": "numero",
    "entidad": "entidad",
    "entidad_entidad": "entidad",
    "superficie_sembrada_ha": "superficie_sembrada_ha",
    "superficie_cosechada_ha": "superficie_cosechada_ha",
    "superficie_siniestrada_ha": "superficie_siniestrada_ha",
    "produccion": "produccion",
    "produccion_produccion": "produccion",
    "rendimiento_udm_ha": "rendimiento_udm_ha",
    "rendimiento_udm_ha_rendimiento_udm_ha": "rendimiento_udm_ha",
    "pmr_mxn_udm": "pmr_mxn_udm",
    "pmr_udm_pmr_udm": "pmr_mxn_udm",
    "valor_produccion_miles_pesos": "valor_produccion_miles_pesos",
    "valor_produccion_miles_de_pesos_valor_produccion_miles_de_pesos": "valor_produccion_miles_pesos",
    "cierre_crop_label_raw": "cierre_crop_label_raw",
    "cultivo_cierre_agricola_original": "cierre_crop_label_raw",
    "cierre_unit_label": "cierre_unit_label",
    "unidad_cierre_agricola": "cierre_unit_label",
    "cierre_crop_name": "cierre_crop_name",
    "cultivo_cierre_agricola": "cierre_crop_name",
    "query_year": "query_year",
    "anio_consulta": "query_year",
    "source_name": "source_name",
    "nombre_fuente": "source_name",
    "run_date": "run_date",
    "fecha_corrida": "run_date",
    "canonical_product": "canonical_product",
    "producto_canonico": "canonical_product",
}

AVANCE_READ_COLUMN_MAP = {
    "numero": "numero",
    "entidad": "entidad",
    "entidad_entidad": "entidad",
    "superficie_sembrada_ha": "superficie_sembrada_ha",
    "superficie_cosechada_ha": "superficie_cosechada_ha",
    "superficie_siniestrada_ha": "superficie_siniestrada_ha",
    "produccion": "produccion",
    "produccion_produccion": "produccion",
    "rendimiento_udm_ha": "rendimiento_udm_ha",
    "rendimiento_udm_ha_rendimiento_udm_ha": "rendimiento_udm_ha",
    "avance_crop_label_raw": "avance_crop_label_raw",
    "cultivo_avance_agricola_original": "avance_crop_label_raw",
    "avance_unit_label": "avance_unit_label",
    "unidad_avance_agricola": "avance_unit_label",
    "avance_crop_name": "avance_crop_name",
    "cultivo_avance_agricola": "avance_crop_name",
    "query_year": "query_year",
    "anio_consulta": "query_year",
    "query_month": "query_month",
    "mes_consulta": "query_month",
    "query_month_label": "query_month_label",
    "mes_consulta_nombre": "query_month_label",
    "report_cutoff_label": "report_cutoff_label",
    "situacion_corte": "report_cutoff_label",
    "source_name": "source_name",
    "nombre_fuente": "source_name",
    "canonical_product": "canonical_product",
    "producto_canonico": "canonical_product",
}

MASTER_PANEL_COLUMNS = [
    "run_date",
    "canonical_product",
    "source",
    "comparison_price_mxn",
    "price_basis",
    "raw_price_mxn",
    "unit_label",
    "source_page",
    "product_raw",
    "product_inferred",
    "search_terms_used",
    "source_record_count",
    "sniim_daily_mean_mxn",
    "sniim_daily_median_mxn",
    "sniim_daily_min_mxn",
    "sniim_daily_max_mxn",
    "avance_total_superficie_sembrada_ha",
    "avance_total_superficie_cosechada_ha",
    "avance_total_superficie_siniestrada_ha",
    "avance_total_produccion",
    "avance_yield_weighted_udm_ha",
    "avance_rows_used",
    "avance_crop_name",
    "avance_crop_label_raw",
    "avance_report_cutoff_label",
    "avance_cutoff_date",
    "cierre_annual_weighted_pmr_mxn_udm",
    "cierre_rows_used",
    "cierre_total_produccion",
    "cierre_crop_name",
    "cierre_crop_label_raw",
]


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def _normalize_key(value: object) -> str:
    text = str(value).strip()
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return re.sub(r"_+", "_", normalized).strip("_")


def _normalize_canonical_product_value(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    normalized = _normalize_key(value)
    return normalized or pd.NA


def _normalize_canonical_product_column(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    if "canonical_product" not in normalized.columns:
        return normalized
    normalized["canonical_product"] = normalized["canonical_product"].map(_normalize_canonical_product_value)
    return normalized


def _read_sheet_with_aliases(path: Path, aliases: Iterable[str], *, fallback_first_sheet: bool = False) -> pd.DataFrame:
    with pd.ExcelFile(path) as excel:
        alias_map = {_normalize_key(name): name for name in excel.sheet_names}
        for alias in aliases:
            resolved = alias_map.get(_normalize_key(alias))
            if resolved:
                return pd.read_excel(path, sheet_name=resolved)
        if fallback_first_sheet and excel.sheet_names:
            return pd.read_excel(path, sheet_name=excel.sheet_names[0])
    raise ValueError(f"No matching sheet found in {path} for aliases: {', '.join(aliases)}")


def _read_data_sheet(path: Path) -> pd.DataFrame:
    return _read_sheet_with_aliases(path, DATA_SHEET_ALIASES, fallback_first_sheet=True)


def _read_meta_sheet(path: Path) -> pd.DataFrame:
    return _read_sheet_with_aliases(path, META_SHEET_ALIASES)


def _read_optional_meta_sheet(path: Path) -> pd.DataFrame:
    try:
        return _read_meta_sheet(path)
    except ValueError:
        return pd.DataFrame()


def _read_failures_sheet(path: Path) -> pd.DataFrame:
    try:
        return _read_sheet_with_aliases(path, FAILURE_SHEET_ALIASES)
    except ValueError:
        return pd.DataFrame()


def _rename_columns(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    renamed = df.copy()
    renamed.columns = [column_map.get(str(column), str(column)) for column in renamed.columns]
    return renamed


def _read_source_workbook(path: Path, source_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data_df = _read_data_sheet(path)
    meta_df = _read_optional_meta_sheet(path)
    failures_df = _read_failures_sheet(path)

    if source_name == "walmart":
        return (
            _normalize_canonical_product_column(_rename_columns(data_df, WALMART_READ_COLUMN_MAP)),
            meta_df,
            failures_df,
        )
    if source_name == "chedraui":
        return (
            _normalize_canonical_product_column(_rename_columns(data_df, CHEDRAUI_READ_COLUMN_MAP)),
            meta_df,
            failures_df,
        )
    if source_name == "sniim":
        return (
            _normalize_canonical_product_column(_rename_columns(data_df, SNIIM_READ_COLUMN_MAP)),
            meta_df,
            failures_df,
        )
    if source_name == "cierre_agricola":
        return (
            _normalize_canonical_product_column(_rename_columns(data_df, CIERRE_READ_COLUMN_MAP)),
            meta_df,
            failures_df,
        )
    if source_name == "avance_agricola":
        return (
            _normalize_canonical_product_column(_rename_columns(data_df, AVANCE_READ_COLUMN_MAP)),
            meta_df,
            failures_df,
        )
    raise ValueError(f"Unsupported source workbook: {source_name}")


def _parse_run_date_from_dir(directory: Path) -> str | None:
    name = directory.name
    try:
        pd.Timestamp(name)
    except ValueError:
        return None
    return name


def _load_daily_source_frames(daily_root: Path, source_name: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for run_dir in sorted(path for path in daily_root.iterdir() if path.is_dir()):
        run_date = _parse_run_date_from_dir(run_dir)
        if not run_date:
            continue

        workbook_path = run_dir / f"{source_name}_{run_date}.xlsx"
        if not workbook_path.exists():
            continue

        data_df, _meta_df, _failures_df = _read_source_workbook(workbook_path, source_name)
        data_df = data_df.copy()
        if "run_date" not in data_df.columns:
            data_df["run_date"] = run_date
        if "source_name" not in data_df.columns:
            data_df["source_name"] = source_name
        frames.append(data_df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_cierre_crop_name_map(daily_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for run_dir in sorted(path for path in daily_root.iterdir() if path.is_dir()):
        snapshot_path = run_dir / "products_snapshot.xlsx"
        if not snapshot_path.exists():
            continue
        try:
            configs = load_products_config(snapshot_path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Skipping unreadable products snapshot %s: %s", snapshot_path, exc)
            continue
        for config in configs:
            if config.cierre_crop_name:
                mapping[_normalize_key(config.cierre_crop_name)] = _normalize_canonical_product_value(
                    config.canonical_product
                )
    return mapping


def _load_avance_crop_name_map(daily_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for run_dir in sorted(path for path in daily_root.iterdir() if path.is_dir()):
        snapshot_path = run_dir / "products_snapshot.xlsx"
        if not snapshot_path.exists():
            continue
        try:
            configs = load_products_config(snapshot_path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Skipping unreadable products snapshot %s: %s", snapshot_path, exc)
            continue
        for config in configs:
            if config.avance_crop_name:
                mapping[_normalize_key(config.avance_crop_name)] = _normalize_canonical_product_value(
                    config.canonical_product
                )
    return mapping


def _derive_query_year_from_path(path: Path) -> int | None:
    match = re.search(r"(20\d{2})", path.stem)
    if not match:
        return None
    return int(match.group(1))


SPANISH_MONTH_ALIASES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _derive_query_month_from_path(path: Path) -> int | None:
    normalized_parts = [_normalize_key(part) for part in path.stem.split("_")]
    for part in normalized_parts:
        if part.isdigit():
            value = int(part)
            if 1 <= value <= 12:
                return value
        month_value = SPANISH_MONTH_ALIASES.get(part)
        if month_value:
            return month_value
    return None


def _derive_canonical_product_from_path(path: Path) -> str | None:
    stem = path.stem
    stem = re.sub(
        r"[_-]?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|[1-9]|1[0-2])$",
        "",
        stem,
        flags=re.IGNORECASE,
    ).strip("_- ")
    stem = re.sub(r"[_-]?(20\d{2})$", "", stem).strip("_- ")
    if not stem:
        return None
    normalized = _normalize_key(stem.replace("_", " ").replace("-", " ").strip())
    return normalized or None


def _strip_trailing_unit_from_crop_label(raw_label: str | None, unit_label: str | None) -> str | None:
    if not raw_label:
        return None
    if not unit_label:
        return raw_label.strip()
    suffix = f"({unit_label})"
    text = raw_label.strip()
    if text.endswith(suffix):
        return text[: -len(suffix)].strip()
    return text


def _resolve_canonical_product_for_cierre(
    df: pd.DataFrame,
    crop_name_map: dict[str, str],
    *,
    path_canonical_product: str | None = None,
) -> pd.DataFrame:
    resolved = df.copy()

    if "canonical_product" not in resolved.columns:
        resolved["canonical_product"] = pd.NA

    def _lookup(row: pd.Series) -> object:
        existing = row.get("canonical_product")
        if pd.notna(existing) and str(existing).strip():
            return existing

        crop_name = row.get("cierre_crop_name")
        if pd.notna(crop_name):
            matched = crop_name_map.get(_normalize_key(crop_name))
            if matched:
                return matched

        raw_label = _strip_trailing_unit_from_crop_label(
            row.get("cierre_crop_label_raw"),
            row.get("cierre_unit_label"),
        )
        if raw_label:
            matched = crop_name_map.get(_normalize_key(raw_label))
            if matched:
                return matched

        if path_canonical_product:
            return path_canonical_product

        return pd.NA

    resolved["canonical_product"] = resolved.apply(_lookup, axis=1)
    return _normalize_canonical_product_column(resolved)


def _resolve_canonical_product_for_avance(
    df: pd.DataFrame,
    crop_name_map: dict[str, str],
    *,
    path_canonical_product: str | None = None,
) -> pd.DataFrame:
    resolved = df.copy()

    if "canonical_product" not in resolved.columns:
        resolved["canonical_product"] = pd.NA

    def _lookup(row: pd.Series) -> object:
        existing = row.get("canonical_product")
        if pd.notna(existing) and str(existing).strip():
            return existing

        crop_name = row.get("avance_crop_name")
        if pd.notna(crop_name):
            matched = crop_name_map.get(_normalize_key(crop_name))
            if matched:
                return matched

        raw_label = _strip_trailing_unit_from_crop_label(
            row.get("avance_crop_label_raw"),
            row.get("avance_unit_label"),
        )
        if raw_label:
            matched = crop_name_map.get(_normalize_key(raw_label))
            if matched:
                return matched

        if path_canonical_product:
            return path_canonical_product
        return pd.NA

    resolved["canonical_product"] = resolved.apply(_lookup, axis=1)
    return _normalize_canonical_product_column(resolved)


def _load_cierre_frames(cierre_root: Path, daily_root: Path) -> pd.DataFrame:
    crop_name_map = _load_cierre_crop_name_map(daily_root)
    frames: list[pd.DataFrame] = []
    seen_paths: set[Path] = set()

    for workbook_path in sorted(cierre_root.rglob("*.xlsx")):
        resolved_path = workbook_path.resolve()
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)

        try:
            data_df, _meta_df, _failures_df = _read_source_workbook(workbook_path, "cierre_agricola")
        except Exception:
            continue

        if "pmr_mxn_udm" not in data_df.columns:
            continue

        normalized = data_df.copy()
        if "query_year" not in normalized.columns:
            normalized["query_year"] = _derive_query_year_from_path(workbook_path)
        if "source_name" not in normalized.columns:
            normalized["source_name"] = "cierre_agricola"
        normalized = _resolve_canonical_product_for_cierre(
            normalized,
            crop_name_map,
            path_canonical_product=_derive_canonical_product_from_path(workbook_path),
        )
        frames.append(normalized)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _pick_latest_avance_exports(avance_root: Path) -> dict[tuple[str, int, int], Path]:
    latest: dict[tuple[str, int, int], tuple[float, Path]] = {}
    for workbook_path in sorted(avance_root.rglob("*.xlsx")):
        try:
            data_df, _meta_df, _failures_df = _read_source_workbook(workbook_path, "avance_agricola")
        except Exception:
            continue

        if data_df.empty:
            continue

        year_value = data_df.get("query_year")
        month_value = data_df.get("query_month")
        year = int(year_value.dropna().iloc[0]) if year_value is not None and not year_value.dropna().empty else None
        month = (
            int(month_value.dropna().iloc[0])
            if month_value is not None and not month_value.dropna().empty
            else _derive_query_month_from_path(workbook_path)
        )
        if year is None:
            year = _derive_query_year_from_path(workbook_path)

        canonical_product = _derive_canonical_product_from_path(workbook_path)
        if canonical_product is None or year is None or month is None:
            continue

        key = (_normalize_key(canonical_product), int(year), int(month))
        candidate = (workbook_path.stat().st_mtime, workbook_path)
        previous = latest.get(key)
        if previous is None or candidate[0] >= previous[0]:
            latest[key] = candidate

    return {key: value[1] for key, value in latest.items()}


def _load_avance_frames(avance_root: Path, daily_root: Path) -> pd.DataFrame:
    crop_name_map = _load_avance_crop_name_map(daily_root)
    frames: list[pd.DataFrame] = []
    for workbook_path in _pick_latest_avance_exports(avance_root).values():
        data_df, _meta_df, _failures_df = _read_source_workbook(workbook_path, "avance_agricola")
        if data_df.empty:
            continue

        normalized = data_df.copy()
        if "query_year" not in normalized.columns or normalized["query_year"].isna().all():
            normalized["query_year"] = _derive_query_year_from_path(workbook_path)
        if "query_month" not in normalized.columns or normalized["query_month"].isna().all():
            normalized["query_month"] = _derive_query_month_from_path(workbook_path)
        if "source_name" not in normalized.columns:
            normalized["source_name"] = "avance_agricola"
        normalized = _resolve_canonical_product_for_avance(
            normalized,
            crop_name_map,
            path_canonical_product=_derive_canonical_product_from_path(workbook_path),
        )
        frames.append(normalized)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _parse_avance_cutoff_date(value: object) -> date | pd.NaT:
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    match = re.search(
        r"(\d{1,2})\s+de\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+de\s+(20\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return pd.NaT
    day = int(match.group(1))
    month = SPANISH_MONTH_ALIASES.get(_normalize_key(match.group(2)))
    year = int(match.group(3))
    if month is None:
        return pd.NaT
    try:
        return date(year, month, day)
    except ValueError:
        return pd.NaT


def build_avance_monthly_stats(avance_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "canonical_product",
        "query_year",
        "query_month",
        "query_month_label",
        "avance_month_key",
        "avance_total_superficie_sembrada_ha",
        "avance_total_superficie_cosechada_ha",
        "avance_total_superficie_siniestrada_ha",
        "avance_total_produccion",
        "avance_yield_weighted_udm_ha",
        "avance_rows_used",
        "avance_unit_label",
        "avance_crop_name",
        "avance_crop_label_raw",
        "avance_report_cutoff_label",
        "avance_cutoff_date",
        "avance_sembrada_vs_cosechada_ratio",
        "avance_siniestrada_share",
    ]
    if avance_df.empty:
        return pd.DataFrame(columns=columns)

    working = _normalize_canonical_product_column(avance_df.copy())
    for column in (
        "superficie_sembrada_ha",
        "superficie_cosechada_ha",
        "superficie_siniestrada_ha",
        "produccion",
        "rendimiento_udm_ha",
        "query_year",
        "query_month",
    ):
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")

    working = working[
        working["canonical_product"].notna() & working["query_year"].notna() & working["query_month"].notna()
    ].copy()
    if working.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        working.groupby(["canonical_product", "query_year", "query_month"], dropna=False)
        .agg(
            avance_total_superficie_sembrada_ha=("superficie_sembrada_ha", "sum"),
            avance_total_superficie_cosechada_ha=("superficie_cosechada_ha", "sum"),
            avance_total_superficie_siniestrada_ha=("superficie_siniestrada_ha", "sum"),
            avance_total_produccion=("produccion", "sum"),
            avance_rows_used=("entidad", "count"),
            avance_unit_label=("avance_unit_label", "first"),
            avance_crop_name=("avance_crop_name", "first"),
            avance_crop_label_raw=("avance_crop_label_raw", "first"),
            avance_report_cutoff_label=("report_cutoff_label", "first"),
            query_month_label=("query_month_label", "first"),
        )
        .reset_index()
    )

    cosechada = grouped["avance_total_superficie_cosechada_ha"].where(
        grouped["avance_total_superficie_cosechada_ha"].notna() & (grouped["avance_total_superficie_cosechada_ha"] > 0)
    )
    sembrada = grouped["avance_total_superficie_sembrada_ha"].where(
        grouped["avance_total_superficie_sembrada_ha"].notna() & (grouped["avance_total_superficie_sembrada_ha"] > 0)
    )
    grouped["avance_yield_weighted_udm_ha"] = grouped["avance_total_produccion"] / cosechada
    grouped["avance_sembrada_vs_cosechada_ratio"] = grouped["avance_total_superficie_cosechada_ha"] / sembrada
    grouped["avance_siniestrada_share"] = grouped["avance_total_superficie_siniestrada_ha"] / sembrada
    grouped["avance_month_key"] = grouped.apply(
        lambda row: f"{int(row['query_year']):04d}-{int(row['query_month']):02d}",
        axis=1,
    )
    grouped["avance_cutoff_date"] = grouped["avance_report_cutoff_label"].map(_parse_avance_cutoff_date)
    grouped["query_year"] = grouped["query_year"].astype(int)
    grouped["query_month"] = grouped["query_month"].astype(int)
    return grouped.reindex(columns=columns)


def build_sniim_daily_stats(sniim_df: pd.DataFrame) -> pd.DataFrame:
    if sniim_df.empty:
        return pd.DataFrame(
            columns=[
                "run_date",
                "canonical_product",
                "sniim_daily_mean_mxn",
                "sniim_daily_median_mxn",
                "sniim_daily_min_mxn",
                "sniim_daily_max_mxn",
                "sniim_source_row_count",
                "producto_nombre_sitio",
            ]
        )

    working = _normalize_canonical_product_column(sniim_df.copy())
    if "producto_nombre_sitio" not in working.columns:
        working["producto_nombre_sitio"] = pd.NA

    grouped = (
        working.groupby(["run_date", "canonical_product"], dropna=False)
        .agg(
            sniim_daily_mean_mxn=("precio_frecuente", "mean"),
            sniim_daily_median_mxn=("precio_frecuente", "median"),
            sniim_daily_min_mxn=("precio_frecuente", "min"),
            sniim_daily_max_mxn=("precio_frecuente", "max"),
            sniim_source_row_count=("precio_frecuente", "count"),
            producto_nombre_sitio=("producto_nombre_sitio", "first"),
        )
        .reset_index()
    )
    return grouped


def build_retail_daily_panel(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "run_date",
                "canonical_product",
                "source",
                "comparison_price_mxn",
                "price_basis",
                "raw_price_mxn",
                "unit_label",
                "source_page",
                "product_raw",
                "product_inferred",
                "search_terms_used",
            ]
        )

    panel = _normalize_canonical_product_column(df.copy())
    for column in ("source_page", "product_raw", "product_inferred", "search_terms_used"):
        if column not in panel.columns:
            panel[column] = pd.NA
    panel["source"] = source_name
    panel["comparison_price_mxn"] = panel["estimated_price_per_kg_mxn"].where(
        panel["estimated_price_per_kg_mxn"].notna(),
        panel["price_mxn"],
    )
    panel["price_basis"] = panel["estimated_price_per_kg_mxn"].notna().map(
        {True: "estimated_price_per_kg_mxn", False: "price_mxn_fallback"}
    )
    panel["raw_price_mxn"] = panel["price_mxn"]
    panel["unit_label"] = panel["unit_raw"]
    panel["source_record_count"] = 1
    return panel[
        [
            "run_date",
            "canonical_product",
            "source",
            "comparison_price_mxn",
            "price_basis",
            "raw_price_mxn",
            "unit_label",
            "source_page",
            "product_raw",
            "product_inferred",
            "search_terms_used",
            "source_record_count",
        ]
    ]


def build_cierre_annual_stats(cierre_df: pd.DataFrame) -> pd.DataFrame:
    if cierre_df.empty:
        return pd.DataFrame(
            columns=[
                "query_year",
                "canonical_product",
                "cierre_unit_label",
                "cierre_annual_weighted_pmr_mxn_udm",
                "cierre_rows_used",
                "cierre_total_produccion",
                "cierre_crop_name",
                "cierre_crop_label_raw",
            ]
        )

    normalized = _normalize_canonical_product_column(cierre_df.copy())
    valid = normalized[
        normalized["canonical_product"].notna()
        & normalized["pmr_mxn_udm"].notna()
        & normalized["produccion"].notna()
        & (normalized["produccion"] > 0)
    ].copy()

    if valid.empty:
        return pd.DataFrame(
            columns=[
                "query_year",
                "canonical_product",
                "cierre_unit_label",
                "cierre_annual_weighted_pmr_mxn_udm",
                "cierre_rows_used",
                "cierre_total_produccion",
                "cierre_crop_name",
                "cierre_crop_label_raw",
            ]
        )

    valid["weighted_pmr_component"] = valid["pmr_mxn_udm"] * valid["produccion"]
    grouped = (
        valid.groupby(["query_year", "canonical_product", "cierre_unit_label"], dropna=False)
        .agg(
            cierre_rows_used=("pmr_mxn_udm", "size"),
            cierre_total_produccion=("produccion", "sum"),
            cierre_weighted_pmr_sum=("weighted_pmr_component", "sum"),
            cierre_crop_name=("cierre_crop_name", "first"),
            cierre_crop_label_raw=("cierre_crop_label_raw", "first"),
        )
        .reset_index()
    )
    grouped["cierre_annual_weighted_pmr_mxn_udm"] = (
        grouped["cierre_weighted_pmr_sum"] / grouped["cierre_total_produccion"]
    )
    grouped = grouped.drop(columns=["cierre_weighted_pmr_sum"])
    return grouped


def _choose_primary_cierre_unit(cierre_annual_stats: pd.DataFrame) -> pd.DataFrame:
    if cierre_annual_stats.empty:
        return cierre_annual_stats
    ordered = cierre_annual_stats.sort_values(
        ["query_year", "canonical_product", "cierre_total_produccion", "cierre_rows_used"],
        ascending=[True, True, False, False],
        kind="stable",
    )
    return ordered.drop_duplicates(subset=["query_year", "canonical_product"], keep="first")


def _build_base_daily_keyframe(
    sniim_stats: pd.DataFrame,
    walmart_panel: pd.DataFrame,
    chedraui_panel: pd.DataFrame,
) -> pd.DataFrame:
    frames = [
        sniim_stats[["run_date", "canonical_product"]] if not sniim_stats.empty else pd.DataFrame(),
        walmart_panel[["run_date", "canonical_product"]] if not walmart_panel.empty else pd.DataFrame(),
        chedraui_panel[["run_date", "canonical_product"]] if not chedraui_panel.empty else pd.DataFrame(),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["run_date", "canonical_product", "query_year", "query_month"])

    base = pd.concat(frames, ignore_index=True).drop_duplicates().sort_values(["run_date", "canonical_product"])
    timestamps = pd.to_datetime(base["run_date"])
    base["query_year"] = timestamps.dt.year
    base["query_month"] = timestamps.dt.month
    return base.reset_index(drop=True)


def _build_sniim_panel(sniim_stats: pd.DataFrame) -> pd.DataFrame:
    if sniim_stats.empty:
        return pd.DataFrame(columns=MASTER_PANEL_COLUMNS)

    panel = sniim_stats.copy()
    panel["source"] = "sniim"
    panel["comparison_price_mxn"] = panel["sniim_daily_mean_mxn"]
    panel["price_basis"] = SNIIM_PANEL_PRICE_BASIS
    panel["raw_price_mxn"] = panel["sniim_daily_mean_mxn"]
    panel["unit_label"] = SNIIM_PANEL_UNIT_LABEL
    panel["source_page"] = pd.NA
    panel["product_raw"] = pd.NA
    panel["product_inferred"] = pd.NA
    panel["search_terms_used"] = pd.NA
    panel["source_record_count"] = panel["sniim_source_row_count"]
    panel["avance_total_superficie_sembrada_ha"] = pd.NA
    panel["avance_total_superficie_cosechada_ha"] = pd.NA
    panel["avance_total_superficie_siniestrada_ha"] = pd.NA
    panel["avance_total_produccion"] = pd.NA
    panel["avance_yield_weighted_udm_ha"] = pd.NA
    panel["avance_rows_used"] = pd.NA
    panel["avance_crop_name"] = pd.NA
    panel["avance_crop_label_raw"] = pd.NA
    panel["avance_report_cutoff_label"] = pd.NA
    panel["avance_cutoff_date"] = pd.NaT
    panel["cierre_annual_weighted_pmr_mxn_udm"] = pd.NA
    panel["cierre_rows_used"] = pd.NA
    panel["cierre_total_produccion"] = pd.NA
    panel["cierre_crop_name"] = pd.NA
    panel["cierre_crop_label_raw"] = pd.NA
    return panel.reindex(columns=MASTER_PANEL_COLUMNS)


def _build_avance_panel(avance_monthly_stats: pd.DataFrame) -> pd.DataFrame:
    if avance_monthly_stats.empty:
        return pd.DataFrame(columns=MASTER_PANEL_COLUMNS)

    panel = avance_monthly_stats.copy()
    panel["run_date"] = panel["avance_cutoff_date"].where(
        panel["avance_cutoff_date"].notna(),
        pd.to_datetime(
            panel["query_year"].astype(int).astype(str)
            + "-"
            + panel["query_month"].astype(int).astype(str).str.zfill(2)
            + "-01"
        ),
    )
    panel["source"] = "avance_agricola"
    panel["comparison_price_mxn"] = pd.NA
    panel["price_basis"] = AVANCE_PANEL_PRICE_BASIS
    panel["raw_price_mxn"] = pd.NA
    panel["unit_label"] = panel["avance_unit_label"]
    panel["source_page"] = pd.NA
    panel["product_raw"] = pd.NA
    panel["product_inferred"] = pd.NA
    panel["search_terms_used"] = pd.NA
    panel["source_record_count"] = panel["avance_rows_used"]
    panel["sniim_daily_mean_mxn"] = pd.NA
    panel["sniim_daily_median_mxn"] = pd.NA
    panel["sniim_daily_min_mxn"] = pd.NA
    panel["sniim_daily_max_mxn"] = pd.NA
    panel["cierre_annual_weighted_pmr_mxn_udm"] = pd.NA
    panel["cierre_rows_used"] = pd.NA
    panel["cierre_total_produccion"] = pd.NA
    panel["cierre_crop_name"] = pd.NA
    panel["cierre_crop_label_raw"] = pd.NA
    return panel.reindex(columns=MASTER_PANEL_COLUMNS)


def _build_cierre_daily_panel(base_daily_keys: pd.DataFrame, cierre_annual_stats: pd.DataFrame) -> pd.DataFrame:
    if base_daily_keys.empty or cierre_annual_stats.empty:
        return pd.DataFrame(columns=MASTER_PANEL_COLUMNS)

    primary = _choose_primary_cierre_unit(cierre_annual_stats)
    panel = base_daily_keys.merge(primary, on=["query_year", "canonical_product"], how="left")
    panel = panel[panel["cierre_annual_weighted_pmr_mxn_udm"].notna()].copy()
    if panel.empty:
        return pd.DataFrame(columns=MASTER_PANEL_COLUMNS)

    panel["source"] = "cierre_agricola"
    panel["comparison_price_mxn"] = panel["cierre_annual_weighted_pmr_mxn_udm"]
    panel["price_basis"] = CIERRE_PANEL_PRICE_BASIS
    panel["raw_price_mxn"] = panel["cierre_annual_weighted_pmr_mxn_udm"]
    panel["unit_label"] = panel["cierre_unit_label"]
    panel["source_page"] = pd.NA
    panel["product_raw"] = pd.NA
    panel["product_inferred"] = pd.NA
    panel["search_terms_used"] = pd.NA
    panel["source_record_count"] = panel["cierre_rows_used"]
    panel["sniim_daily_mean_mxn"] = pd.NA
    panel["sniim_daily_median_mxn"] = pd.NA
    panel["sniim_daily_min_mxn"] = pd.NA
    panel["sniim_daily_max_mxn"] = pd.NA
    panel["avance_total_superficie_sembrada_ha"] = pd.NA
    panel["avance_total_superficie_cosechada_ha"] = pd.NA
    panel["avance_total_superficie_siniestrada_ha"] = pd.NA
    panel["avance_total_produccion"] = pd.NA
    panel["avance_yield_weighted_udm_ha"] = pd.NA
    panel["avance_rows_used"] = pd.NA
    panel["avance_crop_name"] = pd.NA
    panel["avance_crop_label_raw"] = pd.NA
    panel["avance_report_cutoff_label"] = pd.NA
    panel["avance_cutoff_date"] = pd.NaT
    return panel.reindex(columns=MASTER_PANEL_COLUMNS)


def _ensure_compare_columns(compare_daily_wide: pd.DataFrame) -> pd.DataFrame:
    ensured = compare_daily_wide.copy()
    for column in (
        "avance_total_superficie_sembrada_ha",
        "avance_total_superficie_cosechada_ha",
        "avance_total_superficie_siniestrada_ha",
        "avance_total_produccion",
        "avance_yield_weighted_udm_ha",
        "avance_rows_used",
        "avance_unit_label",
        "avance_crop_name",
        "avance_crop_label_raw",
        "avance_report_cutoff_label",
        "avance_cutoff_date",
        "avance_sembrada_vs_cosechada_ratio",
        "avance_siniestrada_share",
        "avance_month_key",
    ):
        if column not in ensured.columns:
            ensured[column] = pd.NA
    for column in (
        "cierre_annual_weighted_pmr_mxn_udm",
        "cierre_unit_label",
        "cierre_rows_used",
        "cierre_total_produccion",
        "cierre_crop_name",
        "cierre_crop_label_raw",
    ):
        if column not in ensured.columns:
            ensured[column] = pd.NA
    return ensured


def build_master_tables(
    daily_root: Path,
    avance_root: Path,
    cierre_root: Path | None = None,
) -> dict[str, pd.DataFrame]:
    sniim_df = _load_daily_source_frames(daily_root, "sniim")
    walmart_df = _load_daily_source_frames(daily_root, "walmart")
    chedraui_df = _load_daily_source_frames(daily_root, "chedraui")
    avance_df = _load_avance_frames(avance_root, daily_root)
    cierre_df = _load_cierre_frames(cierre_root, daily_root) if cierre_root and cierre_root.exists() else pd.DataFrame()

    sniim_stats = build_sniim_daily_stats(sniim_df)
    walmart_panel = build_retail_daily_panel(walmart_df, "walmart")
    chedraui_panel = build_retail_daily_panel(chedraui_df, "chedraui")
    avance_monthly_stats = build_avance_monthly_stats(avance_df)
    cierre_annual_stats = build_cierre_annual_stats(cierre_df)

    base_daily_keys = _build_base_daily_keyframe(sniim_stats, walmart_panel, chedraui_panel)
    avance_daily_context = base_daily_keys.merge(
        avance_monthly_stats,
        on=["canonical_product", "query_year", "query_month"],
        how="left",
    )
    cierre_daily_panel = _build_cierre_daily_panel(base_daily_keys, cierre_annual_stats)

    panel_frames = [
        _build_sniim_panel(sniim_stats),
        walmart_panel.reindex(columns=MASTER_PANEL_COLUMNS),
        chedraui_panel.reindex(columns=MASTER_PANEL_COLUMNS),
        _build_avance_panel(avance_monthly_stats),
        cierre_daily_panel.reindex(columns=MASTER_PANEL_COLUMNS),
    ]
    panel_frames = [frame for frame in panel_frames if not frame.empty]
    if panel_frames:
        panel_daily_long = pd.DataFrame.from_records(
            [record for frame in panel_frames for record in frame.to_dict(orient="records")],
            columns=MASTER_PANEL_COLUMNS,
        )
    else:
        panel_daily_long = pd.DataFrame(columns=MASTER_PANEL_COLUMNS)
    if not panel_daily_long.empty:
        panel_daily_long = panel_daily_long.sort_values(["run_date", "canonical_product", "source"]).reset_index(
            drop=True
        )

    compare_daily_wide = base_daily_keys.copy()
    if not sniim_stats.empty:
        compare_daily_wide = compare_daily_wide.merge(sniim_stats, on=["run_date", "canonical_product"], how="left")
    if not avance_daily_context.empty:
        compare_daily_wide = compare_daily_wide.merge(
            avance_daily_context[
                [
                    "run_date",
                    "canonical_product",
                    "avance_total_superficie_sembrada_ha",
                    "avance_total_superficie_cosechada_ha",
                    "avance_total_superficie_siniestrada_ha",
                    "avance_total_produccion",
                    "avance_yield_weighted_udm_ha",
                    "avance_rows_used",
                    "avance_unit_label",
                    "avance_crop_name",
                    "avance_crop_label_raw",
                    "avance_report_cutoff_label",
                    "avance_cutoff_date",
                    "avance_sembrada_vs_cosechada_ratio",
                    "avance_siniestrada_share",
                    "avance_month_key",
                ]
            ],
            on=["run_date", "canonical_product"],
            how="left",
        )

    for source_name, source_panel in (("walmart", walmart_panel), ("chedraui", chedraui_panel)):
        if source_panel.empty:
            continue
        wide_source = source_panel[
            [
                "run_date",
                "canonical_product",
                "comparison_price_mxn",
                "price_basis",
                "raw_price_mxn",
                "unit_label",
                "source_page",
                "product_raw",
                "product_inferred",
                "search_terms_used",
            ]
        ].rename(
            columns={
                "comparison_price_mxn": f"{source_name}_comparison_mxn",
                "price_basis": f"{source_name}_price_basis",
                "raw_price_mxn": f"{source_name}_raw_price_mxn",
                "unit_label": f"{source_name}_unit_label",
                "source_page": f"{source_name}_source_page",
                "product_raw": f"{source_name}_product_raw",
                "product_inferred": f"{source_name}_product_inferred",
                "search_terms_used": f"{source_name}_search_terms_used",
            }
        )
        compare_daily_wide = compare_daily_wide.merge(wide_source, on=["run_date", "canonical_product"], how="left")

    if not cierre_daily_panel.empty:
        cierre_wide = cierre_daily_panel[
            [
                "run_date",
                "canonical_product",
                "cierre_annual_weighted_pmr_mxn_udm",
                "unit_label",
                "cierre_rows_used",
                "cierre_total_produccion",
                "cierre_crop_name",
                "cierre_crop_label_raw",
            ]
        ].rename(columns={"unit_label": "cierre_unit_label"})
        compare_daily_wide = compare_daily_wide.merge(cierre_wide, on=["run_date", "canonical_product"], how="left")
    compare_daily_wide = _ensure_compare_columns(compare_daily_wide)

    if not compare_daily_wide.empty:
        compare_daily_wide = compare_daily_wide.sort_values(["run_date", "canonical_product"]).reset_index(drop=True)

    coverage = compare_daily_wide[["run_date", "canonical_product"]].copy()
    if not coverage.empty:
        def _present(column: str) -> pd.Series:
            if column in compare_daily_wide.columns:
                return compare_daily_wide[column].notna()
            return pd.Series([False] * len(compare_daily_wide), index=compare_daily_wide.index)

        coverage["has_sniim"] = _present("sniim_daily_mean_mxn")
        coverage["has_walmart"] = _present("walmart_comparison_mxn")
        coverage["has_chedraui"] = _present("chedraui_comparison_mxn")
        coverage["has_avance"] = _present("avance_rows_used")
        coverage["has_cierre"] = _present("cierre_annual_weighted_pmr_mxn_udm")
        count_columns = ["has_sniim", "has_walmart", "has_chedraui", "has_avance"]
        if not cierre_annual_stats.empty:
            count_columns.append("has_cierre")
        coverage["available_sources_count"] = coverage[count_columns].sum(axis=1)
        coverage["missing_sources_count"] = len(count_columns) - coverage["available_sources_count"]

    return {
        "panel_daily_long": panel_daily_long,
        "compare_daily_wide": compare_daily_wide,
        "sniim_daily_stats": sniim_stats,
        "avance_monthly_stats": avance_monthly_stats,
        "avance_entity_monthly": avance_df,
        "cierre_annual_stats": cierre_annual_stats,
        "coverage": coverage,
    }


def write_master_workbook(output_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def build_master_workbook(
    daily_root: Path,
    avance_root: Path,
    output_path: Path,
    cierre_root: Path | None = None,
) -> dict[str, pd.DataFrame]:
    tables = build_master_tables(daily_root, avance_root, cierre_root)
    write_master_workbook(output_path, tables)
    return tables


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a master comparative workbook from daily source exports.")
    parser.add_argument("--daily-root", required=True, type=Path, help="Root directory with dated daily run folders")
    parser.add_argument(
        "--avance-root",
        required=True,
        type=Path,
        help="Root directory with normalized Avance Agricola xlsx exports",
    )
    parser.add_argument(
        "--cierre-root",
        required=False,
        type=Path,
        help="Root directory with normalized Cierre Agricola xlsx exports",
    )
    parser.add_argument("--output", required=True, type=Path, help="Path to the master comparative workbook")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    if not args.daily_root.exists():
        LOGGER.error("Daily root not found: %s", args.daily_root)
        return 1
    if not args.avance_root.exists():
        LOGGER.error("Avance root not found: %s", args.avance_root)
        return 1
    if args.cierre_root and not args.cierre_root.exists():
        LOGGER.error("Cierre root not found: %s", args.cierre_root)
        return 1

    tables = build_master_workbook(args.daily_root, args.avance_root, args.output, args.cierre_root)
    LOGGER.info(
        "Master workbook written to %s with %s compare rows",
        args.output,
        len(tables["compare_daily_wide"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
