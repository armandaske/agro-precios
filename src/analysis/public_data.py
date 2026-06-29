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


def load_existing_climate_history(output_path: Path) -> pd.DataFrame:
    if not output_path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(output_path)
    if "fecha" in frame.columns:
        frame["fecha"] = pd.to_datetime(frame["fecha"], errors="coerce")
    return frame


def determine_nasa_fetch_window(
    history: pd.DataFrame,
    output_path: Path,
    *,
    end_date: str,
    start_date: str | None = None,
    merge_existing: bool = False,
    lookback_days: int = 40,
) -> tuple[str, str, pd.DataFrame]:
    if history.empty or history["fecha"].dropna().empty:
        raise ValueError("No hay historial de presas para derivar la ventana climatica.")

    earliest_reservoir_date = pd.Timestamp(history["fecha"].min()).normalize()
    resolved_end = pd.Timestamp(end_date).normalize()
    if pd.isna(resolved_end):
        raise ValueError(f"Fecha final invalida: {end_date}")
    if resolved_end < earliest_reservoir_date:
        raise ValueError(
            f"La fecha final {resolved_end.date()} es anterior al historial minimo de presas {earliest_reservoir_date.date()}."
        )

    resolved_start = (
        pd.Timestamp(start_date).normalize() if start_date else earliest_reservoir_date
    )
    if pd.isna(resolved_start):
        raise ValueError(f"Fecha inicial invalida: {start_date}")

    existing = pd.DataFrame()
    if merge_existing:
        existing = load_existing_climate_history(output_path)
        if not existing.empty and "fecha" in existing.columns:
            existing_max = pd.Timestamp(existing["fecha"].max()).normalize()
            overlap_start = max(
                existing_max - pd.Timedelta(days=lookback_days),
                earliest_reservoir_date,
            )
            resolved_start = max(resolved_start, overlap_start)

    if resolved_start > resolved_end:
        raise ValueError(
            f"La ventana climatica quedo invalida: {resolved_start.date()} > {resolved_end.date()}."
        )

    return (
        resolved_start.date().isoformat(),
        resolved_end.date().isoformat(),
        existing,
    )


def merge_climate_history(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    frames = [frame.copy() for frame in (existing, incoming) if not frame.empty]
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True, sort=False)
    if "fecha" in merged.columns:
        merged["fecha"] = pd.to_datetime(merged["fecha"], errors="coerce")
    if "id_conagua" in merged.columns:
        merged["id_conagua"] = merged["id_conagua"].astype(str)
    merged = merged.sort_values(["id_conagua", "fecha"], na_position="last")
    merged = merged.drop_duplicates(["id_conagua", "fecha"], keep="last")
    return merged.reset_index(drop=True)


def fetch_nasa_power_weather(
    reservoir_root: Path,
    output_path: Path,
    *,
    start_date: str | None = None,
    end_date: str,
    state: str | None = None,
    limit: int | None = None,
    pause_seconds: float = 0.2,
    timeout: int = 90,
    merge_existing: bool = False,
    lookback_days: int = 40,
) -> pd.DataFrame:
    history = load_reservoir_history(reservoir_root)
    start_date_resolved, end_date_resolved, existing = determine_nasa_fetch_window(
        history,
        output_path,
        end_date=end_date,
        start_date=start_date,
        merge_existing=merge_existing,
        lookback_days=lookback_days,
    )
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
                    "start": start_date_resolved.replace("-", ""),
                    "end": end_date_resolved.replace("-", ""),
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
    incoming = aggregate_weather_to_decena(pd.concat(frames, ignore_index=True))
    decena = merge_climate_history(existing, incoming) if merge_existing else incoming
    write_parquet_with_metadata(
        decena,
        output_path,
        metadata={
            "generado_en": datetime.now().isoformat(timespec="seconds"),
            "fuente": NASA_POWER_URL,
            "parametros": ["PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "EVPTRNS"],
            "fecha_inicio_consulta": start_date_resolved,
            "fecha_fin_consulta": end_date_resolved,
            "fecha_minima_archivo": decena["fecha"].min() if not decena.empty else None,
            "fecha_maxima_archivo": decena["fecha"].max() if not decena.empty else None,
            "merge_existing": merge_existing,
            "lookback_days": lookback_days if merge_existing else None,
            "presas_solicitadas": len(locations),
            "presas_exitosas": int(incoming["id_conagua"].nunique()),
            "filas_archivo": len(decena),
            "errores": failures,
        },
    )
    return decena
