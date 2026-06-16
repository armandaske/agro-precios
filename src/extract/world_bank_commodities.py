from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

WORLD_BANK_MONTHLY_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)


def fetch_world_bank_pink_sheet(
    output_dir: Path,
    *,
    url: str = WORLD_BANK_MONTHLY_URL,
    timeout: int = 60,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"world_bank_pink_sheet_monthly_{timestamp}.xlsx"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return output_path


def _parse_world_bank_month(value: Any) -> pd.Timestamp:
    text = str(value).strip()
    if "M" in text:
        year, month = text.split("M", 1)
        return pd.Timestamp(year=int(year), month=int(month), day=1)
    return pd.to_datetime(value, errors="coerce")


def normalize_world_bank_prices(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    if raw.shape[0] < 7:
        return _empty_frame()

    series_names = raw.iloc[4]
    units = raw.iloc[5]
    data = raw.iloc[6:].copy()
    date_column = data.columns[0]
    data["fecha"] = data[date_column].map(_parse_world_bank_month)

    frames: list[pd.DataFrame] = []
    for column in data.columns:
        if column in {date_column, "fecha"}:
            continue
        serie = series_names.get(column)
        if pd.isna(serie) or not str(serie).strip():
            continue
        raw_values = data[column].astype(object)
        raw_values = raw_values.mask(raw_values.isin(["…", "...", ""]), pd.NA)
        values = pd.to_numeric(raw_values, errors="coerce")
        frame = pd.DataFrame(
            {
                "fecha": data["fecha"],
                "serie": str(serie).strip(),
                "precio_original": values,
                "moneda": "USD",
                "unidad_origen": str(units.get(column)).strip() if pd.notna(units.get(column)) else "",
                "frecuencia": "mensual",
                "fuente": "world_bank",
                "archivo_fuente": str(path),
            }
        )
        frames.append(frame)

    if not frames:
        return _empty_frame()
    return (
        pd.concat(frames, ignore_index=True)
        .dropna(subset=["fecha", "precio_original"])
        .reset_index(drop=True)
    )


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
