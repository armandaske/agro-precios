from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

# Allow execution both as `python scripts/build_master_price_workbook.py`
# and `python -m scripts.build_master_price_workbook`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_daily_extracts import load_products_config
from src.extract.spreadsheet_localization import (
    ARCHIVO_INSTANTANEA_PRODUCTOS_ALIASES,
    MASTER_WORKBOOK_SHEET_NAMES,
)

LOGGER = logging.getLogger("build_master_price_workbook")

DATA_SHEET_ALIASES = ("datos", "data")
META_SHEET_ALIASES = ("metadatos", "meta")
FAILURE_SHEET_ALIASES = ("errores", "failures")
SNIIM_PANEL_UNIT_LABEL = "kg_calculado"
CIERRE_PANEL_PRICE_BASIS = "pmr_mxn_udm_weighted_by_produccion"
SNIIM_PANEL_PRICE_BASIS = "precio_frecuente_mean"

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
    "cierre_annual_weighted_pmr_mxn_udm",
    "cierre_rows_used",
    "cierre_total_produccion",
    "cierre_crop_name",
    "cierre_crop_label_raw",
]

MASTER_PANEL_EXPORT_COLUMN_MAP = {
    "run_date": "fecha_corrida",
    "canonical_product": "producto_canonico",
    "source": "fuente",
    "comparison_price_mxn": "precio_comparable_mxn",
    "price_basis": "base_precio",
    "raw_price_mxn": "precio_original_mxn",
    "unit_label": "unidad",
    "source_page": "pagina_fuente",
    "product_raw": "producto_original",
    "product_inferred": "producto_inferido",
    "search_terms_used": "terminos_busqueda_utilizados",
    "source_record_count": "registros_fuente",
    "sniim_daily_mean_mxn": "sniim_precio_promedio_diario_mxn",
    "sniim_daily_median_mxn": "sniim_precio_mediana_diaria_mxn",
    "sniim_daily_min_mxn": "sniim_precio_minimo_diario_mxn",
    "sniim_daily_max_mxn": "sniim_precio_maximo_diario_mxn",
    "cierre_annual_weighted_pmr_mxn_udm": "cierre_pmr_anual_ponderado_mxn_udm",
    "cierre_rows_used": "cierre_registros_utilizados",
    "cierre_total_produccion": "cierre_produccion_total",
    "cierre_crop_name": "cultivo_cierre_agricola",
    "cierre_crop_label_raw": "cultivo_cierre_agricola_original",
}

SNIIM_STATS_EXPORT_COLUMN_MAP = {
    "run_date": "fecha_corrida",
    "canonical_product": "producto_canonico",
    "sniim_daily_mean_mxn": "sniim_precio_promedio_diario_mxn",
    "sniim_daily_median_mxn": "sniim_precio_mediana_diaria_mxn",
    "sniim_daily_min_mxn": "sniim_precio_minimo_diario_mxn",
    "sniim_daily_max_mxn": "sniim_precio_maximo_diario_mxn",
    "sniim_source_row_count": "sniim_registros_fuente",
    "producto_nombre_sitio": "producto_sniim",
}

CIERRE_ANNUAL_EXPORT_COLUMN_MAP = {
    "query_year": "anio_consulta",
    "canonical_product": "producto_canonico",
    "cierre_unit_label": "unidad_cierre_agricola",
    "cierre_annual_weighted_pmr_mxn_udm": "cierre_pmr_anual_ponderado_mxn_udm",
    "cierre_rows_used": "cierre_registros_utilizados",
    "cierre_total_produccion": "cierre_produccion_total",
    "cierre_crop_name": "cultivo_cierre_agricola",
    "cierre_crop_label_raw": "cultivo_cierre_agricola_original",
}

COMPARE_WIDE_EXPORT_COLUMN_MAP = {
    "run_date": "fecha_corrida",
    "canonical_product": "producto_canonico",
    "query_year": "anio_consulta",
    "sniim_daily_mean_mxn": "sniim_precio_promedio_diario_mxn",
    "sniim_daily_median_mxn": "sniim_precio_mediana_diaria_mxn",
    "sniim_daily_min_mxn": "sniim_precio_minimo_diario_mxn",
    "sniim_daily_max_mxn": "sniim_precio_maximo_diario_mxn",
    "sniim_source_row_count": "sniim_registros_fuente",
    "producto_nombre_sitio": "producto_sniim",
    "walmart_comparison_mxn": "walmart_precio_comparable_mxn",
    "walmart_price_basis": "walmart_base_precio",
    "walmart_raw_price_mxn": "walmart_precio_original_mxn",
    "walmart_unit_label": "walmart_unidad",
    "walmart_source_page": "walmart_pagina_fuente",
    "walmart_product_raw": "walmart_producto_original",
    "walmart_product_inferred": "walmart_producto_inferido",
    "walmart_search_terms_used": "walmart_terminos_busqueda_utilizados",
    "chedraui_comparison_mxn": "chedraui_precio_comparable_mxn",
    "chedraui_price_basis": "chedraui_base_precio",
    "chedraui_raw_price_mxn": "chedraui_precio_original_mxn",
    "chedraui_unit_label": "chedraui_unidad",
    "chedraui_source_page": "chedraui_pagina_fuente",
    "chedraui_product_raw": "chedraui_producto_original",
    "chedraui_product_inferred": "chedraui_producto_inferido",
    "chedraui_search_terms_used": "chedraui_terminos_busqueda_utilizados",
    "cierre_annual_weighted_pmr_mxn_udm": "cierre_pmr_anual_ponderado_mxn_udm",
    "cierre_unit_label": "unidad_cierre_agricola",
    "cierre_rows_used": "cierre_registros_utilizados",
    "cierre_total_produccion": "cierre_produccion_total",
    "cierre_crop_name": "cultivo_cierre_agricola",
    "cierre_crop_label_raw": "cultivo_cierre_agricola_original",
}

COVERAGE_EXPORT_COLUMN_MAP = {
    "run_date": "fecha_corrida",
    "canonical_product": "producto_canonico",
    "has_sniim": "tiene_sniim",
    "has_walmart": "tiene_walmart",
    "has_chedraui": "tiene_chedraui",
    "has_cierre": "tiene_cierre_agricola",
    "available_sources_count": "fuentes_disponibles_conteo",
    "missing_sources_count": "fuentes_faltantes_conteo",
}


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def _normalize_key(value: object) -> str:
    text = str(value).strip()
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return re.sub(r"_+", "_", normalized).strip("_")


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


def _export_columns(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    return _rename_columns(df, column_map)


def _find_first_existing_path(directory: Path, candidate_names: Iterable[str]) -> Path | None:
    for candidate_name in candidate_names:
        candidate_path = directory / candidate_name
        if candidate_path.exists():
            return candidate_path
    return None


def _read_source_workbook(path: Path, source_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data_df = _read_data_sheet(path)
    meta_df = _read_optional_meta_sheet(path)
    failures_df = _read_failures_sheet(path)

    if source_name == "walmart":
        return (
            _rename_columns(data_df, WALMART_READ_COLUMN_MAP),
            meta_df,
            failures_df,
        )
    if source_name == "chedraui":
        return (
            _rename_columns(data_df, CHEDRAUI_READ_COLUMN_MAP),
            meta_df,
            failures_df,
        )
    if source_name == "sniim":
        return (
            _rename_columns(data_df, SNIIM_READ_COLUMN_MAP),
            meta_df,
            failures_df,
        )
    if source_name == "cierre_agricola":
        return (
            _rename_columns(data_df, CIERRE_READ_COLUMN_MAP),
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
        snapshot_path = _find_first_existing_path(run_dir, ARCHIVO_INSTANTANEA_PRODUCTOS_ALIASES)
        if snapshot_path is None:
            continue
        try:
            configs = load_products_config(snapshot_path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Skipping unreadable products snapshot %s: %s", snapshot_path, exc)
            continue
        for config in configs:
            if config.cierre_crop_name:
                mapping[_normalize_key(config.cierre_crop_name)] = config.canonical_product
    return mapping


def _derive_query_year_from_path(path: Path) -> int | None:
    match = re.search(r"(20\d{2})", path.stem)
    if not match:
        return None
    return int(match.group(1))


def _derive_canonical_product_from_path(path: Path) -> str | None:
    stem = path.stem
    stem = re.sub(r"[_-]?(20\d{2})$", "", stem).strip("_- ")
    if not stem:
        return None
    return stem.replace("_", " ").replace("-", " ").strip() or None


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
    return resolved


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

    working = sniim_df.copy()
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

    panel = df.copy()
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

    valid = cierre_df[
        cierre_df["canonical_product"].notna()
        & cierre_df["pmr_mxn_udm"].notna()
        & cierre_df["produccion"].notna()
        & (cierre_df["produccion"] > 0)
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
        return pd.DataFrame(columns=["run_date", "canonical_product", "query_year"])

    base = pd.concat(frames, ignore_index=True).drop_duplicates().sort_values(["run_date", "canonical_product"])
    base["query_year"] = pd.to_datetime(base["run_date"]).dt.year
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
    return panel.reindex(columns=MASTER_PANEL_COLUMNS)


def _ensure_cierre_compare_columns(compare_daily_wide: pd.DataFrame) -> pd.DataFrame:
    ensured = compare_daily_wide.copy()
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


def build_master_tables(daily_root: Path, cierre_root: Path) -> dict[str, pd.DataFrame]:
    sniim_df = _load_daily_source_frames(daily_root, "sniim")
    walmart_df = _load_daily_source_frames(daily_root, "walmart")
    chedraui_df = _load_daily_source_frames(daily_root, "chedraui")
    cierre_df = _load_cierre_frames(cierre_root, daily_root)

    sniim_stats = build_sniim_daily_stats(sniim_df)
    walmart_panel = build_retail_daily_panel(walmart_df, "walmart")
    chedraui_panel = build_retail_daily_panel(chedraui_df, "chedraui")
    cierre_annual_stats = build_cierre_annual_stats(cierre_df)

    base_daily_keys = _build_base_daily_keyframe(sniim_stats, walmart_panel, chedraui_panel)
    cierre_daily_panel = _build_cierre_daily_panel(base_daily_keys, cierre_annual_stats)

    panel_frames = [
        _build_sniim_panel(sniim_stats),
        walmart_panel.reindex(columns=MASTER_PANEL_COLUMNS),
        chedraui_panel.reindex(columns=MASTER_PANEL_COLUMNS),
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
    compare_daily_wide = _ensure_cierre_compare_columns(compare_daily_wide)

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
        coverage["has_cierre"] = _present("cierre_annual_weighted_pmr_mxn_udm")
        coverage["available_sources_count"] = coverage[
            ["has_sniim", "has_walmart", "has_chedraui", "has_cierre"]
        ].sum(axis=1)
        coverage["missing_sources_count"] = 4 - coverage["available_sources_count"]

    return {
        MASTER_WORKBOOK_SHEET_NAMES["panel_diario_largo"]: _export_columns(
            panel_daily_long,
            MASTER_PANEL_EXPORT_COLUMN_MAP,
        ),
        MASTER_WORKBOOK_SHEET_NAMES["comparativo_diario_ancho"]: _export_columns(
            compare_daily_wide,
            COMPARE_WIDE_EXPORT_COLUMN_MAP,
        ),
        MASTER_WORKBOOK_SHEET_NAMES["estadisticas_diarias_sniim"]: _export_columns(
            sniim_stats,
            SNIIM_STATS_EXPORT_COLUMN_MAP,
        ),
        MASTER_WORKBOOK_SHEET_NAMES["estadisticas_anuales_cierre"]: _export_columns(
            cierre_annual_stats,
            CIERRE_ANNUAL_EXPORT_COLUMN_MAP,
        ),
        MASTER_WORKBOOK_SHEET_NAMES["cobertura"]: _export_columns(
            coverage,
            COVERAGE_EXPORT_COLUMN_MAP,
        ),
    }


def write_master_workbook(output_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def build_master_workbook(daily_root: Path, cierre_root: Path, output_path: Path) -> dict[str, pd.DataFrame]:
    tables = build_master_tables(daily_root, cierre_root)
    write_master_workbook(output_path, tables)
    return tables


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construye el libro maestro comparativo a partir de corridas diarias.")
    parser.add_argument("--daily-root", required=True, type=Path, help="Directorio raiz con carpetas de corridas diarias")
    parser.add_argument(
        "--cierre-root",
        required=True,
        type=Path,
        help="Directorio raiz con exportes normalizados de Cierre Agricola en xlsx",
    )
    parser.add_argument("--output", required=True, type=Path, help="Ruta de salida del libro maestro comparativo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()

    if not args.daily_root.exists():
        LOGGER.error("No se encontró el directorio daily-root: %s", args.daily_root)
        return 1
    if not args.cierre_root.exists():
        LOGGER.error("No se encontró el directorio cierre-root: %s", args.cierre_root)
        return 1

    tables = build_master_workbook(args.daily_root, args.cierre_root, args.output)
    LOGGER.info(
        "Libro maestro escrito en %s con %s filas comparativas",
        args.output,
        len(tables[MASTER_WORKBOOK_SHEET_NAMES["comparativo_diario_ancho"]]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
