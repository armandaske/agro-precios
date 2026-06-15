from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.analysis.common import decena_to_date, write_parquet_with_metadata
from src.analysis.water_risk import load_reservoir_history

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def parse_nasa_power_payload(
    payload: dict[str, Any],
    *,
    id_conagua: str,
    latitude: float,
    longitude: float,
) -> pd.DataFrame:
    parameters = payload.get("properties", {}).get("parameter", {})
    all_dates = sorted(
        {
            date_key
            for values in parameters.values()
            if isinstance(values, dict)
            for date_key in values
        }
    )
    rows = []
    for date_key in all_dates:
        rows.append(
            {
                "id_conagua": id_conagua,
                "fecha_diaria": pd.to_datetime(date_key, format="%Y%m%d", errors="coerce"),
                "latitud": latitude,
                "longitud": longitude,
                "precipitacion_mm": parameters.get("PRECTOTCORR", {}).get(date_key),
                "temperatura_c": parameters.get("T2M", {}).get(date_key),
                "temperatura_max_c": parameters.get("T2M_MAX", {}).get(date_key),
                "temperatura_min_c": parameters.get("T2M_MIN", {}).get(date_key),
                "evapotranspiracion_mm": parameters.get("EVPTRNS", {}).get(date_key),
            }
        )
    frame = pd.DataFrame(rows)
    for column in (
        "precipitacion_mm",
        "temperatura_c",
        "temperatura_max_c",
        "temperatura_min_c",
        "evapotranspiracion_mm",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").replace(-999, pd.NA)
    return frame


def aggregate_weather_to_decena(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.dropna(subset=["fecha_diaria"]).copy()
    frame["anio"] = frame["fecha_diaria"].dt.year
    frame["mes"] = frame["fecha_diaria"].dt.month
    frame["decena"] = pd.cut(
        frame["fecha_diaria"].dt.day,
        bins=[0, 10, 20, 31],
        labels=[1, 2, 3],
    ).astype(int)
    aggregated = (
        frame.groupby(["id_conagua", "anio", "mes", "decena"], as_index=False)
        .agg(
            latitud=("latitud", "first"),
            longitud=("longitud", "first"),
            precipitacion_mm=("precipitacion_mm", "sum"),
            temperatura_c=("temperatura_c", "mean"),
            temperatura_max_c=("temperatura_max_c", "max"),
            temperatura_min_c=("temperatura_min_c", "min"),
            evapotranspiracion_mm=("evapotranspiracion_mm", "sum"),
            dias_observados=("fecha_diaria", "nunique"),
        )
    )
    aggregated["fecha"] = aggregated.apply(
        lambda row: decena_to_date(row["anio"], row["mes"], row["decena"]),
        axis=1,
    )
    aggregated["fuente_clima"] = "NASA_POWER_DAILY_API"
    return aggregated


def fetch_nasa_power_weather(
    reservoir_root: Path,
    output_path: Path,
    *,
    start_date: str,
    end_date: str,
    state: str | None = None,
    limit: int | None = None,
    pause_seconds: float = 0.2,
    timeout: int = 90,
) -> pd.DataFrame:
    history = load_reservoir_history(reservoir_root)
    locations = (
        history.dropna(subset=["latitud", "longitud"])
        .sort_values("fecha")
        .groupby("id_conagua", as_index=False)
        .tail(1)
    )
    if state:
        locations = locations.loc[locations["estado"].str.casefold() == state.casefold()]
    if limit:
        locations = locations.head(limit)
    session = requests.Session()
    frames: list[pd.DataFrame] = []
    failures: list[dict[str, str]] = []
    for row in locations.itertuples():
        try:
            response = session.get(
                NASA_POWER_URL,
                params={
                    "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,EVPTRNS",
                    "community": "AG",
                    "longitude": row.longitud,
                    "latitude": row.latitud,
                    "start": start_date.replace("-", ""),
                    "end": end_date.replace("-", ""),
                    "format": "JSON",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            frames.append(
                parse_nasa_power_payload(
                    response.json(),
                    id_conagua=row.id_conagua,
                    latitude=float(row.latitud),
                    longitude=float(row.longitud),
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"id_conagua": row.id_conagua, "error": str(exc)})
        time.sleep(pause_seconds)
    if not frames:
        raise RuntimeError(f"NASA POWER no produjo datos. Errores: {failures[:3]}")
    decena = aggregate_weather_to_decena(pd.concat(frames, ignore_index=True))
    write_parquet_with_metadata(
        decena,
        output_path,
        metadata={
            "generado_en": datetime.now().isoformat(timespec="seconds"),
            "fuente": NASA_POWER_URL,
            "parametros": ["PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "EVPTRNS"],
            "fecha_inicio": start_date,
            "fecha_fin": end_date,
            "presas_solicitadas": len(locations),
            "presas_exitosas": int(decena["id_conagua"].nunique()),
            "errores": failures,
        },
    )
    return decena
