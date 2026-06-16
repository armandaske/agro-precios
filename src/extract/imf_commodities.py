from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.common import normalize_key


DATE_ALIASES = {"date", "fecha", "period", "time_period", "observation_date"}
SERIES_ALIASES = {"commodity", "serie", "series", "name", "producto", "indicator"}
VALUE_ALIASES = {"value", "precio", "price", "obs_value", "valor"}


def normalize_imf_commodity_file(path: Path) -> pd.DataFrame:
    raw = _read_file(path)
    if raw.empty:
        return _empty_frame()
    raw.columns = [str(column).strip() for column in raw.columns]
    normalized_columns = {column: normalize_key(column) for column in raw.columns}

    date_column = _find_column(normalized_columns, DATE_ALIASES)
    series_column = _find_column(normalized_columns, SERIES_ALIASES)
    value_column = _find_column(normalized_columns, VALUE_ALIASES)

    if date_column and series_column and value_column:
        result = pd.DataFrame(
            {
                "fecha": pd.to_datetime(raw[date_column], errors="coerce"),
                "serie": raw[series_column].astype(str).str.strip(),
                "precio_original": pd.to_numeric(raw[value_column], errors="coerce"),
            }
        )
    else:
        result = _normalize_wide_file(raw)

    if result.empty:
        return _empty_frame()
    result["moneda"] = "USD"
    result["unidad_origen"] = ""
    result["frecuencia"] = "mensual"
    result["fuente"] = "imf"
    result["archivo_fuente"] = str(path)
    return result.dropna(subset=["fecha", "serie", "precio_original"]).reset_index(drop=True)


def _read_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def _find_column(normalized_columns: dict[str, str], candidates: set[str]) -> str | None:
    for column, normalized in normalized_columns.items():
        if normalized in candidates:
            return column
    return None


def _normalize_wide_file(raw: pd.DataFrame) -> pd.DataFrame:
    date_column = raw.columns[0]
    dates = pd.to_datetime(raw[date_column], errors="coerce")
    frames: list[pd.DataFrame] = []
    for column in raw.columns[1:]:
        values = pd.to_numeric(raw[column].replace({"…": pd.NA, "...": pd.NA}), errors="coerce")
        frames.append(
            pd.DataFrame(
                {
                    "fecha": dates,
                    "serie": str(column).strip(),
                    "precio_original": values,
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["fecha", "serie", "precio_original"])
    return pd.concat(frames, ignore_index=True)


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
