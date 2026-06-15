from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.analysis.common import (
    decena_to_date,
    make_regression_pipeline,
    model_feature_importance,
    normalize_key,
    probability_below_from_interval,
    read_sheet_aliases,
    regression_metrics,
    temporal_train_test,
    write_parquet_with_metadata,
)

RESERVOIR_ALIASES = {
    "id_conagua": "id_conagua",
    "nombre_oficial": "nombre_presa",
    "estado": "estado",
    "municipio": "municipio",
    "uso_principal": "uso_principal",
    "distrito_riego": "distrito_riego",
    "anio_dato": "anio",
    "anio": "anio",
    "mes_dato": "mes",
    "mes": "mes",
    "decena_dato": "decena",
    "decena": "decena",
    "porcentaje_almacenamiento": "porcentaje_almacenamiento",
    "almacenamiento_hm3": "almacenamiento_hm3",
    "capacidad_name_hm3": "capacidad_name_hm3",
    "capacidad_namo_hm3": "capacidad_namo_hm3",
    "latitud": "latitud",
    "longitud": "longitud",
    "fuente": "fuente",
    "fecha_extraccion": "fecha_extraccion",
}

BASE_FEATURES = [
    "porcentaje_almacenamiento",
    "almacenamiento_hm3",
    "capacidad_name_hm3",
    "capacidad_namo_hm3",
    "latitud",
    "longitud",
    "mes",
    "decena",
    "mes_seno",
    "mes_coseno",
    "porcentaje_lag_1",
    "porcentaje_lag_2",
    "porcentaje_lag_3",
    "porcentaje_lag_6",
    "porcentaje_lag_12",
    "porcentaje_lag_36",
    "cambio_1_decena",
    "cambio_3_decenas",
    "promedio_3_decenas",
    "promedio_6_decenas",
    "desviacion_6_decenas",
    "estado",
    "uso_principal",
    "distrito_riego",
]


def _standardize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(
        columns={
            column: RESERVOIR_ALIASES.get(normalize_key(column), normalize_key(column))
            for column in frame.columns
        }
    )
    for column in RESERVOIR_ALIASES.values():
        if column not in renamed.columns:
            renamed[column] = pd.NA
    return renamed


def load_reservoir_history(input_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(input_root.rglob("*.xlsx")):
        for aliases in (("presas_periodo",), ("series_presa",)):
            try:
                frame = read_sheet_aliases(path, aliases)
            except Exception:
                continue
            if frame.empty:
                continue
            frame = _standardize_columns(frame)
            frame["archivo_fuente"] = str(path)
            frames.append(frame)

    if not frames:
        raise ValueError(f"No se encontraron observaciones de presas en {input_root}")

    history = pd.concat(frames, ignore_index=True, sort=False)
    for column in (
        "anio",
        "mes",
        "decena",
        "porcentaje_almacenamiento",
        "almacenamiento_hm3",
        "capacidad_name_hm3",
        "capacidad_namo_hm3",
        "latitud",
        "longitud",
    ):
        history[column] = pd.to_numeric(history[column], errors="coerce")
    history = history.dropna(subset=["id_conagua", "anio", "mes", "decena"])
    history["id_conagua"] = history["id_conagua"].astype(str).str.strip()
    history["fecha"] = history.apply(
        lambda row: decena_to_date(row["anio"], row["mes"], row["decena"]),
        axis=1,
    )
    history["fecha_extraccion_orden"] = pd.to_datetime(
        history["fecha_extraccion"], errors="coerce"
    )
    history = history.sort_values(
        ["id_conagua", "fecha", "fecha_extraccion_orden", "archivo_fuente"]
    )
    return history.drop_duplicates(["id_conagua", "fecha"], keep="last").reset_index(drop=True)


def _load_optional_climate(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    climate = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    climate.columns = [normalize_key(column) for column in climate.columns]
    climate = climate.rename(
        columns={
            "date": "fecha",
            "id": "id_conagua",
            "precipitation_mm": "precipitacion_mm",
            "temperature_c": "temperatura_c",
            "drought_index": "indice_sequia",
        }
    )
    climate["fecha"] = pd.to_datetime(climate["fecha"], errors="coerce")
    climate["id_conagua"] = climate["id_conagua"].astype(str)
    return climate


def build_dam_decena_features(
    history: pd.DataFrame,
    climate: pd.DataFrame | None = None,
    *,
    horizons: tuple[int, ...] = (1, 3, 6),
) -> pd.DataFrame:
    features = history.copy().sort_values(["id_conagua", "fecha"]).reset_index(drop=True)
    group = features.groupby("id_conagua", sort=False)["porcentaje_almacenamiento"]
    for lag in (1, 2, 3, 6, 12, 36):
        features[f"porcentaje_lag_{lag}"] = group.shift(lag)
    features["cambio_1_decena"] = (
        features["porcentaje_almacenamiento"] - features["porcentaje_lag_1"]
    )
    features["cambio_3_decenas"] = (
        features["porcentaje_almacenamiento"] - features["porcentaje_lag_3"]
    )
    features["promedio_3_decenas"] = group.transform(
        lambda values: values.shift(1).rolling(3, min_periods=1).mean()
    )
    features["promedio_6_decenas"] = group.transform(
        lambda values: values.shift(1).rolling(6, min_periods=2).mean()
    )
    features["desviacion_6_decenas"] = group.transform(
        lambda values: values.shift(1).rolling(6, min_periods=3).std()
    )
    features["mes_seno"] = np.sin(2 * np.pi * features["mes"] / 12)
    features["mes_coseno"] = np.cos(2 * np.pi * features["mes"] / 12)
    for horizon in horizons:
        features[f"objetivo_porcentaje_h{horizon}"] = group.shift(-horizon)
        features[f"objetivo_almacenamiento_h{horizon}"] = features.groupby(
            "id_conagua", sort=False
        )["almacenamiento_hm3"].shift(-horizon)

    if climate is not None and not climate.empty:
        features = features.merge(climate, on=["id_conagua", "fecha"], how="left")
        for column in ("precipitacion_mm", "temperatura_c", "indice_sequia"):
            if column in features.columns and column not in BASE_FEATURES:
                BASE_FEATURES.append(column)
    return features


def build_state_decena_features(features: pd.DataFrame) -> pd.DataFrame:
    working = features.dropna(subset=["estado", "fecha"]).copy()
    working["capacidad_peso"] = working["capacidad_namo_hm3"].where(
        working["capacidad_namo_hm3"] > 0, working["capacidad_name_hm3"]
    )
    working["almacenamiento_ponderado"] = (
        working["porcentaje_almacenamiento"] * working["capacidad_peso"]
    )
    grouped = (
        working.groupby(["estado", "fecha"], as_index=False)
        .agg(
            porcentaje_promedio=("porcentaje_almacenamiento", "mean"),
            almacenamiento_total_hm3=("almacenamiento_hm3", "sum"),
            capacidad_total_hm3=("capacidad_peso", "sum"),
            almacenamiento_ponderado=("almacenamiento_ponderado", "sum"),
            presas_observadas=("id_conagua", "nunique"),
            presas_bajo_40=("porcentaje_almacenamiento", lambda values: int((values < 40).sum())),
            presas_bajo_25=("porcentaje_almacenamiento", lambda values: int((values < 25).sum())),
            presas_bajo_15=("porcentaje_almacenamiento", lambda values: int((values < 15).sum())),
        )
    )
    grouped["porcentaje_ponderado_capacidad"] = (
        grouped["almacenamiento_ponderado"] / grouped["capacidad_total_hm3"]
    )
    return grouped.drop(columns=["almacenamiento_ponderado"])


def _risk_level(
    predicted_pct: float,
    probability_below_40: float,
    probability_below_25: float,
    probability_below_15: float,
) -> str:
    if predicted_pct < 15 or probability_below_15 >= 0.5:
        return "critico"
    if predicted_pct < 25 or probability_below_25 >= 0.5:
        return "alto"
    if predicted_pct < 40 or probability_below_40 >= 0.5:
        return "medio"
    return "bajo"


def train_water_models(
    features: pd.DataFrame,
    output_dir: Path,
    *,
    horizons: tuple[int, ...] = (1, 3, 6),
    thresholds: tuple[float, ...] = (40.0, 25.0, 15.0),
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest = (
        features.sort_values("fecha").groupby("id_conagua", as_index=False).tail(1).copy()
    )
    latest_cutoff = features["fecha"].max() - pd.Timedelta(days=45)
    latest = latest.loc[latest["fecha"] >= latest_cutoff].copy()
    available_features = [column for column in BASE_FEATURES if column in features.columns]
    metrics: dict[str, Any] = {}
    alerts: list[pd.DataFrame] = []
    importances: list[pd.DataFrame] = []

    for horizon in horizons:
        target = f"objetivo_porcentaje_h{horizon}"
        training = features.dropna(subset=[target, "porcentaje_lag_1"]).copy()
        if len(training) < 200:
            raise ValueError(
                f"No hay suficientes filas para horizonte {horizon}: {len(training)}; minimo 200."
            )
        train_idx, test_idx, cutoff = temporal_train_test(training, "fecha")
        validation_features = [
            column
            for column in available_features
            if training.loc[train_idx, column].notna().any()
        ]
        point_model = make_regression_pipeline(training.loc[train_idx], validation_features)
        point_model.fit(
            training.loc[train_idx, validation_features],
            training.loc[train_idx, target],
        )
        test_prediction = point_model.predict(training.loc[test_idx, validation_features])

        baseline_previous = training.loc[test_idx, "porcentaje_almacenamiento"].to_numpy()
        baseline_year = training.loc[test_idx, "porcentaje_lag_36"].fillna(
            training.loc[test_idx, "porcentaje_almacenamiento"]
        )
        model_metrics = regression_metrics(training.loc[test_idx, target], test_prediction)
        previous_metrics = regression_metrics(
            training.loc[test_idx, target], baseline_previous
        )
        year_metrics = regression_metrics(
            training.loc[test_idx, target], baseline_year.to_numpy()
        )
        candidates = {
            "xgboost": model_metrics["mae"],
            "decena_anterior": previous_metrics["mae"],
            "misma_decena_anio_anterior": year_metrics["mae"],
        }
        operational_method = min(candidates, key=candidates.get)
        operational_validation_prediction = {
            "xgboost": test_prediction,
            "decena_anterior": baseline_previous,
            "misma_decena_anio_anterior": baseline_year.to_numpy(),
        }[operational_method]
        horizon_metrics = {
            "fecha_corte_validacion": cutoff.isoformat(),
            "filas_entrenamiento": int(len(train_idx)),
            "filas_validacion": int(len(test_idx)),
            "modelo_xgboost": model_metrics,
            "base_decena_anterior": previous_metrics,
            "base_misma_decena_anio_anterior": year_metrics,
            "metodo_operativo": operational_method,
            "xgboost_operativo": operational_method == "xgboost",
        }
        residuals = (
            training.loc[test_idx, target].to_numpy()
            - operational_validation_prediction
        )
        lower_residual = float(np.nanquantile(residuals, 0.10))
        upper_residual = float(np.nanquantile(residuals, 0.90))
        metrics[f"horizonte_{horizon}_decenas"] = horizon_metrics

        final_model = make_regression_pipeline(training, available_features)
        final_model.fit(training[available_features], training[target])
        joblib.dump(final_model, output_dir / f"modelo_agua_h{horizon}.joblib")

        predicted = {
            "xgboost": final_model.predict(latest[available_features]),
            "decena_anterior": latest["porcentaje_almacenamiento"].to_numpy(),
            "misma_decena_anio_anterior": latest["porcentaje_lag_36"]
            .fillna(latest["porcentaje_almacenamiento"])
            .to_numpy(),
        }[operational_method]
        horizon_alert = latest[
            [
                "id_conagua",
                "nombre_presa",
                "estado",
                "municipio",
                "fecha",
                "porcentaje_almacenamiento",
                "almacenamiento_hm3",
                "capacidad_namo_hm3",
                "latitud",
                "longitud",
            ]
        ].copy()
        horizon_alert["horizonte_dias"] = horizon * 10
        horizon_alert["metodo_pronostico"] = operational_method
        horizon_alert["porcentaje_pronosticado"] = predicted
        horizon_alert["porcentaje_p10"] = predicted + lower_residual
        horizon_alert["porcentaje_p90"] = predicted + upper_residual
        capacity = pd.to_numeric(horizon_alert["capacidad_namo_hm3"], errors="coerce")
        horizon_alert["almacenamiento_pronosticado_hm3"] = predicted * capacity / 100
        for threshold in thresholds:
            horizon_alert[f"probabilidad_bajo_{int(threshold)}"] = horizon_alert.apply(
                lambda row: probability_below_from_interval(
                    threshold,
                    float(row["porcentaje_pronosticado"]),
                    float(row["porcentaje_p10"]),
                    float(row["porcentaje_p90"]),
                ),
                axis=1,
            )
        horizon_alert["nivel_riesgo"] = horizon_alert.apply(
            lambda row: _risk_level(
                float(row["porcentaje_pronosticado"]),
                float(row["probabilidad_bajo_40"]),
                float(row["probabilidad_bajo_25"]),
                float(row["probabilidad_bajo_15"]),
            ),
            axis=1,
        )
        alerts.append(horizon_alert)

        importance = model_feature_importance(final_model).head(20)
        importance["horizonte_dias"] = horizon * 10
        importances.append(importance)

    alert_frame = pd.concat(alerts, ignore_index=True)
    for threshold in thresholds:
        threshold_int = int(threshold)
        earliest = (
            alert_frame.loc[
                (alert_frame["porcentaje_pronosticado"] < threshold)
                | (alert_frame[f"probabilidad_bajo_{threshold_int}"] >= 0.5)
            ]
            .sort_values("horizonte_dias")
            .groupby("id_conagua", as_index=False)
            .first()[["id_conagua", "horizonte_dias"]]
            .rename(
                columns={
                    "horizonte_dias": f"dias_estimados_bajo_{threshold_int}"
                }
            )
        )
        alert_frame = alert_frame.merge(earliest, on="id_conagua", how="left")
    importance_frame = pd.concat(importances, ignore_index=True)
    return alert_frame, metrics, importance_frame


def write_water_dashboard(alerts: pd.DataFrame, output_path: Path) -> None:
    latest_horizon = int(alerts["horizonte_dias"].min())
    points = alerts.loc[alerts["horizonte_dias"] == latest_horizon].copy()
    records = points.replace({np.nan: None}).to_dict("records")
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('nombre_presa', '')))}</td>"
        f"<td>{html.escape(str(row.get('estado', '')))}</td>"
        f"<td>{float(row.get('porcentaje_almacenamiento') or 0):.1f}%</td>"
        f"<td>{float(row.get('porcentaje_pronosticado') or 0):.1f}%</td>"
        f"<td>{html.escape(str(row.get('nivel_riesgo', '')))}</td>"
        "</tr>"
        for row in sorted(records, key=lambda item: item.get("probabilidad_bajo_40") or 0, reverse=True)[:30]
    )
    payload = json.dumps(records, ensure_ascii=False, default=str)
    output_path.write_text(
        f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Monitoreo de riesgo hidrico</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{{font-family:Arial;margin:24px;color:#17202a}}#map{{height:520px;border-radius:8px}}
table{{border-collapse:collapse;width:100%;margin-top:20px}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}
.critico{{color:#b91c1c}}.alto{{color:#c2410c}}.medio{{color:#a16207}}.bajo{{color:#15803d}}</style>
</head><body><h1>Monitoreo predictivo de riesgo hidrico</h1>
<p>Pronostico operativo a {latest_horizon} dias. Los intervalos y probabilidades provienen de validacion temporal.</p>
<div id="map"></div><table><thead><tr><th>Presa</th><th>Estado</th><th>Actual</th><th>Pronostico</th><th>Riesgo</th></tr></thead>
<tbody>{rows}</tbody></table>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const data={payload}; const map=L.map('map').setView([23.6,-102.5],5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'OpenStreetMap'}}).addTo(map);
const colors={{critico:'#b91c1c',alto:'#ea580c',medio:'#ca8a04',bajo:'#16a34a'}};
data.forEach(d=>{{if(d.latitud!=null&&d.longitud!=null)L.circleMarker([d.latitud,d.longitud],{{
radius:6,color:colors[d.nivel_riesgo]||'#64748b',fillOpacity:.8}}).addTo(map).bindPopup(
`<b>${{d.nombre_presa}}</b><br>${{d.estado}}<br>Actual: ${{Number(d.porcentaje_almacenamiento).toFixed(1)}}%<br>Pronostico: ${{Number(d.porcentaje_pronosticado).toFixed(1)}}%`);}});
</script></body></html>""",
        encoding="utf-8",
    )


def run_water_risk_pipeline(
    input_root: Path,
    output_dir: Path,
    *,
    climate_path: Path | None = None,
    horizons: tuple[int, ...] = (1, 3, 6),
    thresholds: tuple[float, ...] = (40.0, 25.0, 15.0),
) -> dict[str, Any]:
    history = load_reservoir_history(input_root)
    climate = _load_optional_climate(climate_path)
    features = build_dam_decena_features(history, climate, horizons=horizons)
    generated_at = datetime.now().isoformat(timespec="seconds")
    write_parquet_with_metadata(
        features,
        output_dir / "dam_decena_features.parquet",
        metadata={
            "generado_en": generated_at,
            "fuentes": sorted(history["archivo_fuente"].dropna().unique().tolist()),
            "filas": len(features),
            "presas": int(features["id_conagua"].nunique()),
            "fecha_minima": features["fecha"].min(),
            "fecha_maxima": features["fecha"].max(),
            "archivo_clima": str(climate_path) if climate_path else None,
        },
    )
    state_features = build_state_decena_features(features)
    write_parquet_with_metadata(
        state_features,
        output_dir / "state_decena_features.parquet",
        metadata={"generado_en": generated_at, "filas": len(state_features)},
    )
    alerts, metrics, importance = train_water_models(
        features,
        output_dir,
        horizons=horizons,
        thresholds=thresholds,
    )
    alerts.to_csv(output_dir / "alertas_riesgo_hidrico.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_dir / "monitoreo_riesgo_hidrico.xlsx", engine="openpyxl") as writer:
        alerts.to_excel(writer, sheet_name="alertas", index=False)
        state_features.to_excel(writer, sheet_name="riesgo_estatal", index=False)
        importance.to_excel(writer, sheet_name="explicabilidad", index=False)
        pd.DataFrame(
            [{"metrica": key, "valor": json.dumps(value, ensure_ascii=False)} for key, value in metrics.items()]
        ).to_excel(writer, sheet_name="validacion", index=False)
    (output_dir / "metricas_riesgo_hidrico.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_water_dashboard(alerts, output_dir / "monitoreo_riesgo_hidrico.html")
    return {
        "filas_features": len(features),
        "presas": int(features["id_conagua"].nunique()),
        "alertas": len(alerts),
        "metricas": metrics,
    }
