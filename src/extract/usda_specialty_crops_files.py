from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.common import normalize_key


DATE_ALIASES = {
    "date",
    "fecha",
    "report_date",
    "reporte_fecha",
    "shipping_point_date",
    "market_date",
}
PRODUCT_ALIASES = {
    "commodity",
    "product",
    "producto",
    "commodity_name",
    "product_name",
    "variety",
}
UNIT_ALIASES = {"unit", "unidad", "package", "container", "item_size", "pkg"}
PRICE_ALIASES = {"price", "precio", "mostly", "average_price", "avg_price", "weighted_average_price"}
LOW_PRICE_ALIASES = {"low_price", "precio_bajo", "low"}
HIGH_PRICE_ALIASES = {"high_price", "precio_alto", "high"}


def normalize_usda_specialty_crop_file(path: Path) -> pd.DataFrame:
    frames = _read_file(path)
    normalized_frames = [_normalize_sheet(frame, path) for frame in frames if not frame.empty]
    normalized_frames = [frame for frame in normalized_frames if not frame.empty]
    if not normalized_frames:
        return _empty_frame()
    return pd.concat(normalized_frames, ignore_index=True).reset_index(drop=True)


def _read_file(path: Path) -> list[pd.DataFrame]:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        with pd.ExcelFile(path) as workbook:
            return [pd.read_excel(path, sheet_name=sheet) for sheet in workbook.sheet_names]
    return [pd.read_csv(path)]


def _normalize_sheet(raw: pd.DataFrame, path: Path) -> pd.DataFrame:
    raw = raw.copy()
    raw.columns = [str(column).strip() for column in raw.columns]
    normalized_columns = {column: normalize_key(column) for column in raw.columns}
    date_column = _find_column(normalized_columns, DATE_ALIASES)
    product_column = _find_column(normalized_columns, PRODUCT_ALIASES)
    unit_column = _find_column(normalized_columns, UNIT_ALIASES)
    price_column = _find_column(normalized_columns, PRICE_ALIASES)
    low_column = _find_column(normalized_columns, LOW_PRICE_ALIASES)
    high_column = _find_column(normalized_columns, HIGH_PRICE_ALIASES)

    if not date_column or not product_column:
        return _empty_frame()

    if price_column:
        price = pd.to_numeric(raw[price_column], errors="coerce")
    elif low_column and high_column:
        low = pd.to_numeric(raw[low_column], errors="coerce")
        high = pd.to_numeric(raw[high_column], errors="coerce")
        price = (low + high) / 2
    else:
        return _empty_frame()

    unit = raw[unit_column].astype(str).str.strip() if unit_column else ""
    result = pd.DataFrame(
        {
            "fecha": pd.to_datetime(raw[date_column], errors="coerce"),
            "serie": raw[product_column].astype(str).str.strip(),
            "precio_original": price,
            "moneda": "USD",
            "unidad_origen": unit,
            "frecuencia": "diaria",
            "fuente": "usda_ams",
            "archivo_fuente": str(path),
        }
    )
    return result.dropna(subset=["fecha", "serie", "precio_original"]).reset_index(drop=True)


def _find_column(normalized_columns: dict[str, str], candidates: set[str]) -> str | None:
    for column, normalized in normalized_columns.items():
        if normalized in candidates:
            return column
    return None


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "fecha",
            "serie",
            "precio_original",
            "moneda",
            "unidad_origen",
            "frecuencia",
            "fuente",
            "archivo_fuente",
        ]
    )
