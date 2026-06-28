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
    "decena_anual",
    "mes_seno",
    "mes_coseno",
    "decena_anual_seno",
    "decena_anual_coseno",
    "porcentaje_lag_1",
    "porcentaje_lag_2",
    "porcentaje_lag_3",
    "porcentaje_lag_6",
    "porcentaje_lag_12",
    "porcentaje_lag_36",
    "cambio_1_decena",
    "cambio_3_decenas",
    "cambio_6_decenas",
    "promedio_3_decenas",
    "promedio_6_decenas",
    "desviacion_6_decenas",
    "gap_vs_promedio_3",
    "gap_vs_promedio_6",
    "tendencia_3_decenas",
    "tendencia_6_decenas",
    "porcentaje_yoy_gap",
    "estado",
    "uso_principal",
    "distrito_riego",
    "precipitacion_mm",
    "temperatura_c",
    "temperatura_max_c",
    "temperatura_min_c",
    "evapotranspiracion_mm",
    "dias_observados",
    "indice_sequia",
    "balance_hidrico_mm",
    "precipitacion_lag_1",
    "precipitacion_3_decenas",
    "evapotranspiracion_3_decenas",
    "balance_hidrico_3_decenas",
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
        if path.name.startswith("~$"):
            continue
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
            "temperature_max_c": "temperatura_max_c",
            "temperature_min_c": "temperatura_min_c",
            "evapotranspiration_mm": "evapotranspiracion_mm",
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
    horizons: tuple[int, ...] = (3, 6, 9),
) -> pd.DataFrame:
    features = history.copy().sort_values(["id_conagua", "fecha"]).reset_index(drop=True)
    group = features.groupby("id_conagua", sort=False)["porcentaje_almacenamiento"]
    features["decena_anual"] = (features["mes"] - 1) * 3 + features["decena"]
    for lag in (1, 2, 3, 6, 12, 36):
        features[f"porcentaje_lag_{lag}"] = group.shift(lag)
    features["cambio_1_decena"] = (
        features["porcentaje_almacenamiento"] - features["porcentaje_lag_1"]
    )
    features["cambio_3_decenas"] = (
        features["porcentaje_almacenamiento"] - features["porcentaje_lag_3"]
    )
    features["cambio_6_decenas"] = (
        features["porcentaje_almacenamiento"] - features["porcentaje_lag_6"]
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
    features["decena_anual_seno"] = np.sin(2 * np.pi * features["decena_anual"] / 36)
    features["decena_anual_coseno"] = np.cos(2 * np.pi * features["decena_anual"] / 36)
    features["gap_vs_promedio_3"] = (
        features["porcentaje_almacenamiento"] - features["promedio_3_decenas"]
    )
    features["gap_vs_promedio_6"] = (
        features["porcentaje_almacenamiento"] - features["promedio_6_decenas"]
    )
    features["tendencia_3_decenas"] = features["cambio_3_decenas"] / 3
    features["tendencia_6_decenas"] = features["cambio_6_decenas"] / 6
    features["porcentaje_yoy_gap"] = (
        features["porcentaje_almacenamiento"] - features["porcentaje_lag_36"]
    )
    for horizon in horizons:
        features[f"objetivo_porcentaje_h{horizon}"] = group.shift(-horizon)
        features[f"objetivo_almacenamiento_h{horizon}"] = features.groupby(
            "id_conagua", sort=False
        )["almacenamiento_hm3"].shift(-horizon)
        features[f"objetivo_delta_h{horizon}"] = (
            features[f"objetivo_porcentaje_h{horizon}"] - features["porcentaje_almacenamiento"]
        )

    if climate is not None and not climate.empty:
        climate_columns = [
            column
            for column in (
                "id_conagua",
                "fecha",
                "precipitacion_mm",
                "temperatura_c",
                "temperatura_max_c",
                "temperatura_min_c",
                "evapotranspiracion_mm",
                "dias_observados",
                "indice_sequia",
            )
            if column in climate.columns
        ]
        if climate_columns:
            climate = climate[climate_columns].drop_duplicates(["id_conagua", "fecha"])
            features = features.merge(climate, on=["id_conagua", "fecha"], how="left")
            features["balance_hidrico_mm"] = (
                pd.to_numeric(features.get("precipitacion_mm"), errors="coerce")
                - pd.to_numeric(features.get("evapotranspiracion_mm"), errors="coerce")
            )
            if "precipitacion_mm" in features.columns:
                precip_group = features.groupby("id_conagua", sort=False)["precipitacion_mm"]
                features["precipitacion_lag_1"] = precip_group.shift(1)
                features["precipitacion_3_decenas"] = precip_group.transform(
                    lambda values: values.shift(1).rolling(3, min_periods=1).sum()
                )
            if "evapotranspiracion_mm" in features.columns:
                evap_group = features.groupby("id_conagua", sort=False)["evapotranspiracion_mm"]
                features["evapotranspiracion_3_decenas"] = evap_group.transform(
                    lambda values: values.shift(1).rolling(3, min_periods=1).sum()
                )
            if "balance_hidrico_mm" in features.columns:
                balance_group = features.groupby("id_conagua", sort=False)["balance_hidrico_mm"]
                features["balance_hidrico_3_decenas"] = balance_group.transform(
                    lambda values: values.shift(1).rolling(3, min_periods=1).sum()
                )
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


def _seasonal_delta_prediction(
    train_frame: pd.DataFrame,
    predict_frame: pd.DataFrame,
    delta_column: str,
    *,
    default_delta: float,
) -> np.ndarray:
    seasonal_delta = (
        train_frame.groupby("decena_anual", dropna=False)[delta_column]
        .median()
        .to_dict()
    )
    predicted_delta = (
        predict_frame["decena_anual"].map(seasonal_delta).fillna(default_delta).to_numpy()
    )
    current = pd.to_numeric(
        predict_frame["porcentaje_almacenamiento"], errors="coerce"
    ).to_numpy()
    return current + predicted_delta


def train_water_models(
    features: pd.DataFrame,
    output_dir: Path,
    *,
    horizons: tuple[int, ...] = (3, 6, 9),
    thresholds: tuple[float, ...] = (40.0, 25.0, 15.0),
    force_model: str | None = None,
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
        delta_target = f"objetivo_delta_h{horizon}"
        training = features.dropna(
            subset=[target, delta_target, "porcentaje_almacenamiento", "porcentaje_lag_1"]
        ).copy()
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
        delta_model = make_regression_pipeline(training.loc[train_idx], validation_features)
        delta_model.fit(
            training.loc[train_idx, validation_features],
            training.loc[train_idx, delta_target],
        )
        delta_test_prediction = delta_model.predict(
            training.loc[test_idx, validation_features]
        )
        delta_test_prediction_abs = (
            training.loc[test_idx, "porcentaje_almacenamiento"].to_numpy()
            + delta_test_prediction
        )

        baseline_previous = training.loc[test_idx, "porcentaje_almacenamiento"].to_numpy()
        baseline_year = training.loc[test_idx, "porcentaje_lag_36"].fillna(
            training.loc[test_idx, "porcentaje_almacenamiento"]
        )
        baseline_avg3 = training.loc[test_idx, "promedio_3_decenas"].fillna(
            training.loc[test_idx, "porcentaje_almacenamiento"]
        )
        seasonal_delta_default = float(
            training.loc[train_idx, delta_target].median(skipna=True)
        )
        baseline_seasonal_delta = _seasonal_delta_prediction(
            training.loc[train_idx],
            training.loc[test_idx],
            delta_target,
            default_delta=seasonal_delta_default,
        )
        model_metrics = regression_metrics(training.loc[test_idx, target], test_prediction)
        model_delta_metrics = regression_metrics(
            training.loc[test_idx, target], delta_test_prediction_abs
        )
        previous_metrics = regression_metrics(
            training.loc[test_idx, target], baseline_previous
        )
        year_metrics = regression_metrics(
            training.loc[test_idx, target], baseline_year.to_numpy()
        )
        avg3_metrics = regression_metrics(
            training.loc[test_idx, target], baseline_avg3.to_numpy()
        )
        seasonal_delta_metrics = regression_metrics(
            training.loc[test_idx, target], baseline_seasonal_delta
        )
        candidates = {
            "xgboost_nivel": model_metrics["mae"],
            "xgboost_delta": model_delta_metrics["mae"],
            "decena_anterior": previous_metrics["mae"],
            "misma_decena_anio_anterior": year_metrics["mae"],
            "promedio_3_decenas": avg3_metrics["mae"],
            "delta_estacional_mediana": seasonal_delta_metrics["mae"],
        }
        operational_method = min(candidates, key=candidates.get)
        if force_model:
            if force_model not in candidates:
                raise ValueError(
                    "force_model debe ser uno de: xgboost_nivel, xgboost_delta, decena_anterior, misma_decena_anio_anterior, promedio_3_decenas, delta_estacional_mediana."
                )
            operational_method = force_model
        operational_validation_prediction = {
            "xgboost_nivel": test_prediction,
            "xgboost_delta": delta_test_prediction_abs,
            "decena_anterior": baseline_previous,
            "misma_decena_anio_anterior": baseline_year.to_numpy(),
            "promedio_3_decenas": baseline_avg3.to_numpy(),
            "delta_estacional_mediana": baseline_seasonal_delta,
        }[operational_method]
        horizon_metrics = {
            "fecha_corte_validacion": cutoff.isoformat(),
            "filas_entrenamiento": int(len(train_idx)),
            "filas_validacion": int(len(test_idx)),
            "modelo_xgboost_nivel": model_metrics,
            "modelo_xgboost_delta": model_delta_metrics,
            "base_decena_anterior": previous_metrics,
            "base_misma_decena_anio_anterior": year_metrics,
            "base_promedio_3_decenas": avg3_metrics,
            "base_delta_estacional_mediana": seasonal_delta_metrics,
            "metodo_operativo": operational_method,
            "xgboost_operativo": operational_method in {"xgboost_nivel", "xgboost_delta"},
            "metodo_forzado": bool(force_model),
            "metodo_forzado_nombre": force_model if force_model else None,
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
        final_delta_model = make_regression_pipeline(training, available_features)
        final_delta_model.fit(training[available_features], training[delta_target])
        joblib.dump(final_model, output_dir / f"modelo_agua_h{horizon}.joblib")
        joblib.dump(final_delta_model, output_dir / f"modelo_agua_delta_h{horizon}.joblib")
        seasonal_delta_default_full = float(training[delta_target].median(skipna=True))
        baseline_seasonal_delta_latest = _seasonal_delta_prediction(
            training,
            latest,
            delta_target,
            default_delta=seasonal_delta_default_full,
        )

        predicted = {
            "xgboost_nivel": final_model.predict(latest[available_features]),
            "xgboost_delta": latest["porcentaje_almacenamiento"].to_numpy()
            + final_delta_model.predict(latest[available_features]),
            "decena_anterior": latest["porcentaje_almacenamiento"].to_numpy(),
            "misma_decena_anio_anterior": latest["porcentaje_lag_36"]
            .fillna(latest["porcentaje_almacenamiento"])
            .to_numpy(),
            "promedio_3_decenas": latest["promedio_3_decenas"]
            .fillna(latest["porcentaje_almacenamiento"])
            .to_numpy(),
            "delta_estacional_mediana": baseline_seasonal_delta_latest,
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
        horizon_alert["metodo_forzado"] = bool(force_model)
        horizon_alert["metodo_forzado_nombre"] = force_model if force_model else pd.NA
        horizon_alert["porcentaje_pronosticado"] = predicted
        horizon_alert["delta_pronosticado_puntos"] = (
            horizon_alert["porcentaje_pronosticado"] - horizon_alert["porcentaje_almacenamiento"]
        )
        horizon_alert["cambio_pronosticado_pct"] = np.where(
            horizon_alert["porcentaje_almacenamiento"].abs() > 1e-9,
            horizon_alert["porcentaje_pronosticado"] / horizon_alert["porcentaje_almacenamiento"] - 1,
            pd.NA,
        )
        horizon_alert["pronostico_es_persistencia"] = (
            horizon_alert["metodo_pronostico"] == "decena_anterior"
        )
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

        importance_pipeline = final_model
        if operational_method == "xgboost_delta":
            importance_pipeline = final_delta_model
        elif operational_method not in {"xgboost_nivel", "xgboost_delta"}:
            importance_pipeline = (
                final_delta_model
                if model_delta_metrics["mae"] <= model_metrics["mae"]
                else final_model
            )
        importance = model_feature_importance(importance_pipeline).head(20)
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
    horizon_values = sorted(int(value) for value in alerts["horizonte_dias"].dropna().unique())
    default_horizon = horizon_values[0]
    forced_methods = sorted(
        {
            str(value)
            for value in alerts.get("metodo_forzado_nombre", pd.Series(dtype=object)).dropna().unique()
            if str(value).strip()
        }
    )
    persistence_horizons: list[int] = []
    if "pronostico_es_persistencia" in alerts.columns:
        persistence_horizons = sorted(
            int(value)
            for value in alerts.loc[
                alerts["pronostico_es_persistencia"], "horizonte_dias"
            ].dropna().unique()
        )
    sections: list[str] = []
    payload_by_horizon: dict[str, list[dict[str, Any]]] = {}

    for horizon in horizon_values:
        points = alerts.loc[alerts["horizonte_dias"] == horizon].copy()
        records = (
            points.sort_values(
                ["probabilidad_bajo_40", "probabilidad_bajo_25", "probabilidad_bajo_15"],
                ascending=False,
            )
            .replace({np.nan: None})
            .to_dict("records")
        )
        payload_by_horizon[str(horizon)] = records
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(str(row.get('nombre_presa', '')))}</td>"
            f"<td>{html.escape(str(row.get('estado', '')))}</td>"
            f"<td>{float(row.get('porcentaje_almacenamiento') or 0):.1f}%</td>"
            f"<td>{float(row.get('porcentaje_pronosticado') or 0):.1f}%</td>"
            f"<td>{float(row.get('delta_pronosticado_puntos') or 0):+.1f} pts</td>"
            f"<td>{float(row.get('probabilidad_bajo_40') or 0):.1%}</td>"
            f"<td>{html.escape(str(row.get('metodo_pronostico', '')))}</td>"
            f"<td>{html.escape(str(row.get('nivel_riesgo', '')))}</td>"
            "</tr>"
            for row in records
        )
        sections.append(
            f"""<section class="horizon-panel" data-horizon="{horizon}" {"hidden" if horizon != default_horizon else ""}>
<h2>Horizonte a {horizon} dias</h2>
<div class="map" id="map-{horizon}"></div>
<table><thead><tr><th>Presa</th><th>Estado</th><th>Actual</th><th>Pronostico</th><th>Cambio</th><th>Prob. &lt;40%</th><th>Metodo</th><th>Riesgo</th></tr></thead>
<tbody>{rows}</tbody></table></section>"""
        )

    summary_rows = "".join(
        "<tr>"
        f"<td>{horizon}</td>"
        f"<td>{len(alerts.loc[alerts['horizonte_dias'] == horizon])}</td>"
        f"<td>{int((alerts.loc[alerts['horizonte_dias'] == horizon, 'nivel_riesgo'] == 'critico').sum())}</td>"
        f"<td>{int((alerts.loc[alerts['horizonte_dias'] == horizon, 'nivel_riesgo'].isin(['alto', 'critico'])).sum())}</td>"
        "</tr>"
        for horizon in horizon_values
    )
    payload = json.dumps(payload_by_horizon, ensure_ascii=False, default=str)
    output_path.write_text(
        f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Monitoreo de riesgo hidrico</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
body{{font-family:Arial;margin:24px;color:#17202a}}
.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 24px}}
.toolbar button{{padding:10px 14px;border:1px solid #cbd5e1;background:#fff;border-radius:6px;cursor:pointer}}
.toolbar button.active{{background:#17202a;color:#fff;border-color:#17202a}}
.summary-table, table{{border-collapse:collapse;width:100%;margin-top:20px}}
th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}
.map{{height:520px;border-radius:8px}}
.critico{{color:#b91c1c}}.alto{{color:#c2410c}}.medio{{color:#a16207}}.bajo{{color:#15803d}}
.horizon-panel[hidden]{{display:none}}
</style>
</head><body><h1>Monitoreo predictivo de riesgo hidrico</h1>
<p>El tablero muestra de forma separada los horizontes operativos a {", ".join(str(value) for value in horizon_values)} dias. Los intervalos y probabilidades provienen de validacion temporal.</p>
{"<p><strong>Lectura operativa:</strong> los horizontes " + ", ".join(str(value) for value in persistence_horizons) + " dias quedaron en persistencia porque ese baseline supero al resto fuera de muestra.</p>" if persistence_horizons else ""}
{"<p><strong>Modo demo:</strong> el metodo operativo fue forzado a <code>" + ", ".join(forced_methods) + "</code>. Esta salida no respeta la seleccion automatica por mejor MAE fuera de muestra.</p>" if forced_methods else ""}
<table class="summary-table"><thead><tr><th>Horizonte</th><th>Presas evaluadas</th><th>Criticas</th><th>Altas o criticas</th></tr></thead>
<tbody>{summary_rows}</tbody></table>
<div class="toolbar">{"".join(f'<button type="button" data-target=\"{h}\" class=\"{"active" if h == default_horizon else ""}\">{h} dias</button>' for h in horizon_values)}</div>
{"".join(sections)}
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const dataByHorizon={payload};
const colors={{critico:'#b91c1c',alto:'#ea580c',medio:'#ca8a04',bajo:'#16a34a'}};
const maps={{}};
function renderMap(horizon) {{
  if (maps[horizon]) return;
  const map=L.map(`map-${{horizon}}`).setView([23.6,-102.5],5);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'OpenStreetMap'}}).addTo(map);
  (dataByHorizon[horizon] || []).forEach(d=>{{
    if(d.latitud!=null&&d.longitud!=null)L.circleMarker([d.latitud,d.longitud],{{
      radius:6,color:colors[d.nivel_riesgo]||'#64748b',fillOpacity:.8
    }}).addTo(map).bindPopup(
      `<b>${{d.nombre_presa}}</b><br>${{d.estado}}<br>Horizonte: ${{horizon}} dias<br>Actual: ${{Number(d.porcentaje_almacenamiento).toFixed(1)}}%<br>Pronostico: ${{Number(d.porcentaje_pronosticado).toFixed(1)}}%<br>Cambio: ${{Number(d.delta_pronosticado_puntos).toFixed(1)}} pts<br>Metodo: ${{d.metodo_pronostico}}<br>Prob. <40%: ${{(Number(d.probabilidad_bajo_40)*100).toFixed(1)}}%`
    );
  }});
  maps[horizon]=map;
}}
document.querySelectorAll('.toolbar button').forEach(button=>{{
  button.addEventListener('click', ()=>{{
    const target = button.dataset.target;
    document.querySelectorAll('.toolbar button').forEach(node=>node.classList.toggle('active', node===button));
    document.querySelectorAll('.horizon-panel').forEach(panel=>panel.hidden = panel.dataset.horizon !== target);
    renderMap(target);
  }});
}});
renderMap('{default_horizon}');
</script></body></html>""",
        encoding="utf-8",
    )


def run_water_risk_pipeline(
    input_root: Path,
    output_dir: Path,
    *,
    climate_path: Path | None = None,
    horizons: tuple[int, ...] = (3, 6, 9),
    thresholds: tuple[float, ...] = (40.0, 25.0, 15.0),
    force_model: str | None = None,
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
            "metodo_forzado": force_model,
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
        force_model=force_model,
    )
    alerts.to_csv(output_dir / "alertas_riesgo_hidrico.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_dir / "monitoreo_riesgo_hidrico.xlsx", engine="openpyxl") as writer:
        alerts.to_excel(writer, sheet_name="alertas", index=False)
        (
            alerts.groupby("horizonte_dias", as_index=False)
            .agg(
                presas_evaluadas=("id_conagua", "nunique"),
                presas_criticas=("nivel_riesgo", lambda values: int((values == "critico").sum())),
                presas_altas_o_criticas=("nivel_riesgo", lambda values: int(values.isin(["alto", "critico"]).sum())),
                promedio_pronosticado=("porcentaje_pronosticado", "mean"),
                delta_abs_promedio=("delta_pronosticado_puntos", lambda values: float(values.abs().mean())),
                metodo_operativo=("metodo_pronostico", lambda values: values.mode().iloc[0]),
            )
            .sort_values("horizonte_dias")
        ).to_excel(writer, sheet_name="resumen_horizontes", index=False)
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
        "metodo_forzado": force_model,
        "metricas": metrics,
    }
