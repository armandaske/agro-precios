from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

FRED_DEXMXUS_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXMXUS"


def fetch_fred_dexmxus(
    output_dir: Path,
    *,
    url: str = FRED_DEXMXUS_CSV_URL,
    timeout: int = 90,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"fred_dexmxus_{timestamp}.csv"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return output_path


def normalize_fred_dexmxus(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if raw.empty or len(raw.columns) < 2:
        return _empty_frame()

    date_column = raw.columns[0]
    value_column = raw.columns[1]
    values = pd.to_numeric(raw[value_column].replace({".": pd.NA}), errors="coerce")
    result = pd.DataFrame(
        {
            "fecha": pd.to_datetime(raw[date_column], errors="coerce"),
            "serie": "DEXMXUS",
            "precio_original": values,
            "moneda": "MXN",
            "unidad_origen": "MXN por USD",
            "frecuencia": "diaria",
            "fuente": "fred",
            "archivo_fuente": str(path),
        }
    )
    return result.dropna(subset=["fecha", "precio_original"]).reset_index(drop=True)


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
