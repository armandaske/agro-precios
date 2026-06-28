from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.common import (
    make_regression_pipeline,
    model_feature_importance,
    normalize_key,
    normalize_product,
    probability_below_from_interval,
    read_sheet_aliases,
    regression_metrics,
    temporal_train_test,
    write_parquet_with_metadata,
)

SNIIM_ALIASES = {
    "fecha": "fecha_precio",
    "fecha_corrida": "fecha_corrida",
    "run_date": "fecha_corrida",
    "query_start_date": "fecha_consulta",
    "fecha_inicio_consulta_1": "fecha_consulta",
    "fecha_inicio_query": "fecha_consulta",
    "producto_canonico": "cultivo_canonico",
    "canonical_product": "cultivo_canonico",
    "producto_sniim": "producto_sniim",
    "producto_nombre_sitio": "producto_sniim",
    "origen": "origen",
    "destino": "mercado",
    "precio_minimo": "precio_minimo",
    "precio_maximo": "precio_maximo",
    "precio_frecuente": "precio_frecuente",
}

RETAIL_ALIASES = {
    "fecha_corrida": "fecha",
    "run_date": "fecha",
    "producto_canonico": "cultivo_canonico",
    "producto_canonico_1": "cultivo_canonico",
    "canonical_product": "cultivo_canonico",
    "precio_mxn": "precio_mxn",
    "price_mxn": "precio_mxn",
    "precio_estimado_por_kg_mxn": "precio_kg_mxn",
    "estimated_price_per_kg_mxn": "precio_kg_mxn",
}

MODEL_FEATURES = [
    "precio_actual",
    "precio_lag_1",
    "precio_lag_2",
    "precio_lag_7",
    "precio_lag_14",
    "precio_lag_28",
    "promedio_7",
    "promedio_14",
    "promedio_28",
    "volatilidad_7",
    "volatilidad_28",
    "cambio_1",
    "cambio_7",
    "dia_semana",
    "mes",
    "dia_anio_seno",
    "dia_anio_coseno",
    "precio_walmart",
    "precio_chedraui",
    "spread_walmart",
    "spread_chedraui",
    "porcentaje_agua_nacional",
    "cultivo_canonico",
    "mercado",
]
INTERNATIONAL_FEATURE_PREFIX = "intl_"
RETAIL_SOURCES = ("walmart", "chedraui")
WEEKLY_CHART_WEEKS = 16


def _rename_columns(frame: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    renamed = frame.rename(
        columns={
            column: aliases.get(normalize_key(column), normalize_key(column))
            for column in frame.columns
        }
    )
    if renamed.columns.is_unique:
        return renamed
    coalesced: dict[str, pd.Series] = {}
    for column in dict.fromkeys(renamed.columns):
        selected = renamed.loc[:, renamed.columns == column]
        coalesced[column] = (
            selected.iloc[:, 0]
            if selected.shape[1] == 1
            else selected.bfill(axis=1).iloc[:, 0]
        )
    return pd.DataFrame(coalesced, index=renamed.index)


def _display_crop_name(value: str) -> str:
    return str(value).replace("_", " ").strip().capitalize()


def _slugify_filename(value: str) -> str:
    slug = normalize_key(value).replace(" ", "_")
    return slug or "cultivo"


def _format_currency(value: Any) -> str:
    if value is None or pd.isna(value):
        return "s/d"
    return f"${float(value):,.2f}/kg"


def _format_percent(value: Any) -> str:
    if value is None or pd.isna(value):
        return "s/d"
    return f"{float(value):+.1%}"


def _format_integer(value: Any) -> str:
    if value is None or pd.isna(value):
        return "s/d"
    return f"{int(value)}"


def _json_ready(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def _week_start(series: pd.Series) -> pd.Series:
    return series.dt.to_period("W-SUN").dt.start_time


def load_sniim_daily_history(daily_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(daily_root.rglob("sniim_*.xlsx")):
        try:
            frame = read_sheet_aliases(path, ("datos", "data"), fallback_first=True)
        except Exception:
            continue
        if frame.empty:
            continue
        frame = _rename_columns(frame, SNIIM_ALIASES)
        if "cultivo_canonico" not in frame.columns:
            continue
        frame["archivo_fuente"] = str(path)
        frames.append(frame)
    if not frames:
        raise ValueError(f"No se encontraron precios SNIIM utilizables en {daily_root}")

    prices = pd.concat(frames, ignore_index=True, sort=False)
    for column in ("precio_minimo", "precio_maximo", "precio_frecuente"):
        prices[column] = pd.to_numeric(prices.get(column), errors="coerce")
    empty_dates = pd.Series(pd.NaT, index=prices.index, dtype="datetime64[ns]")
    source_date = pd.to_datetime(
        prices.get("fecha_precio", empty_dates),
        dayfirst=True,
        errors="coerce",
    )
    query_date = pd.to_datetime(
        prices.get("fecha_consulta", empty_dates),
        errors="coerce",
    )
    run_date = pd.to_datetime(
        prices.get("fecha_corrida", empty_dates),
        errors="coerce",
    )
    prices["fecha"] = source_date.fillna(query_date).fillna(run_date)
    prices["cultivo_canonico"] = prices["cultivo_canonico"].map(normalize_product)
    prices["mercado"] = prices.get("mercado", "nacional").fillna("nacional").astype(str).str.strip()
    prices["origen"] = prices.get("origen", "sin_origen").fillna("sin_origen").astype(str).str.strip()
    prices = prices.dropna(subset=["fecha", "precio_frecuente"])
    return prices.drop_duplicates(
        ["fecha", "cultivo_canonico", "mercado", "origen", "precio_frecuente"]
    ).reset_index(drop=True)


def _read_retail_source(daily_root: Path, source: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(daily_root.rglob(f"{source}_*.xlsx")):
        try:
            frame = read_sheet_aliases(path, ("datos", "data"), fallback_first=True)
        except Exception:
            continue
        if frame.empty:
            continue
        frame = _rename_columns(frame, RETAIL_ALIASES)
        if "cultivo_canonico" not in frame.columns:
            continue
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["fecha", "cultivo_canonico", f"precio_{source}"])
    retail = pd.concat(frames, ignore_index=True, sort=False)
    retail["fecha"] = pd.to_datetime(retail["fecha"], errors="coerce")
    retail["cultivo_canonico"] = retail["cultivo_canonico"].map(normalize_product)
    precio_kg = pd.to_numeric(
        retail.get("precio_kg_mxn", pd.Series(np.nan, index=retail.index)),
        errors="coerce",
    )
    precio_unitario = pd.to_numeric(
        retail.get("precio_mxn", pd.Series(np.nan, index=retail.index)),
        errors="coerce",
    )
    retail["precio"] = precio_kg.where(precio_kg.notna(), precio_unitario)
    return (
        retail.dropna(subset=["fecha", "cultivo_canonico", "precio"])
        .groupby(["fecha", "cultivo_canonico"], as_index=False)["precio"]
        .median()
        .rename(columns={"precio": f"precio_{source}"})
    )


def build_retail_spreads(daily_root: Path, wholesale: pd.DataFrame) -> pd.DataFrame:
    national = (
        wholesale.groupby(["fecha", "cultivo_canonico"], as_index=False)["precio_frecuente"]
        .median()
        .rename(columns={"precio_frecuente": "precio_mayoreo"})
    )
    spreads = national
    for source in RETAIL_SOURCES:
        spreads = spreads.merge(
            _read_retail_source(daily_root, source),
            on=["fecha", "cultivo_canonico"],
            how="outer",
        )
        price_column = f"precio_{source}"
        spreads[f"spread_{source}"] = (
            spreads[price_column] / spreads["precio_mayoreo"].replace(0, np.nan) - 1
        )
    return spreads


def build_margin_anomalies(spreads: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for source in RETAIL_SOURCES:
        column = f"spread_{source}"
        subset = spreads.dropna(subset=[column]).copy()
        if subset.empty:
            continue
        grouped = subset.groupby("cultivo_canonico")[column]
        subset["mediana_historica"] = grouped.transform("median")
        subset["mad"] = grouped.transform(
            lambda values: np.median(np.abs(values - np.median(values)))
        )
        scale = subset["mad"].where(
            subset["mad"] > 0,
            grouped.transform("std"),
        )
        subset["puntaje_anomalia"] = (
            0.6745 * (subset[column] - subset["mediana_historica"])
            / scale.replace(0, np.nan)
        )
        subset["fuente_retail"] = source
        subset["spread_retail_mayoreo"] = subset[column]
        rows.append(subset)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(
        "puntaje_anomalia", ascending=False
    )


def _daily_market_panel(wholesale: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        wholesale.groupby(["fecha", "cultivo_canonico", "mercado"], as_index=False)
        .agg(
            precio_actual=("precio_frecuente", "median"),
            precio_minimo=("precio_minimo", "min"),
            precio_maximo=("precio_maximo", "max"),
            observaciones=("precio_frecuente", "size"),
        )
    )
    panels: list[pd.DataFrame] = []
    for (crop, market), group in grouped.groupby(["cultivo_canonico", "mercado"]):
        daily = group.set_index("fecha").sort_index().asfreq("D")
        daily["cultivo_canonico"] = crop
        daily["mercado"] = market
        daily["precio_actual"] = daily["precio_actual"].ffill(limit=3)
        daily["precio_minimo"] = daily["precio_minimo"].ffill(limit=3)
        daily["precio_maximo"] = daily["precio_maximo"].ffill(limit=3)
        daily["observaciones"] = daily["observaciones"].fillna(0)
        panels.append(daily.reset_index())
    return pd.concat(panels, ignore_index=True)


def build_weekly_price_comparison(wholesale: pd.DataFrame, spreads: pd.DataFrame) -> pd.DataFrame:
    daily_market = (
        wholesale.groupby(["fecha", "cultivo_canonico", "mercado"], as_index=False)
        .agg(precio_mercado=("precio_frecuente", "median"))
    )
    daily_wholesale = (
        daily_market.groupby(["fecha", "cultivo_canonico"], as_index=False)
        .agg(
            precio_mercados_mediana=("precio_mercado", "median"),
            precio_mercados_min=("precio_mercado", "min"),
            precio_mercados_max=("precio_mercado", "max"),
            mercados_cubiertos=("mercado", "nunique"),
        )
    )
    retail_columns = ["fecha", "cultivo_canonico", "precio_walmart", "precio_chedraui"]
    retail = (
        spreads.loc[:, retail_columns]
        .drop_duplicates(["fecha", "cultivo_canonico"])
        .copy()
    )
    daily = daily_wholesale.merge(retail, on=["fecha", "cultivo_canonico"], how="left")
    daily["semana_inicio"] = _week_start(pd.to_datetime(daily["fecha"], errors="coerce"))
    weekly = (
        daily.groupby(["semana_inicio", "cultivo_canonico"], as_index=False)
        .agg(
            precio_mercados_mediana=("precio_mercados_mediana", "median"),
            precio_mercados_min=("precio_mercados_min", "median"),
            precio_mercados_max=("precio_mercados_max", "median"),
            mercados_cubiertos=("mercados_cubiertos", "max"),
            precio_walmart=("precio_walmart", "median"),
            precio_chedraui=("precio_chedraui", "median"),
            dias_observados=("fecha", "nunique"),
        )
        .sort_values(["cultivo_canonico", "semana_inicio"])
        .reset_index(drop=True)
    )
    crop_group = weekly.groupby("cultivo_canonico", sort=False)
    weekly["cambio_semanal_mercados_pct"] = (
        weekly["precio_mercados_mediana"] / crop_group["precio_mercados_mediana"].shift(1) - 1
    )
    for source in RETAIL_SOURCES:
        price_column = f"precio_{source}"
        weekly[f"cambio_semanal_{source}_pct"] = (
            weekly[price_column] / crop_group[price_column].shift(1) - 1
        )
        weekly[f"spread_{source}_vs_mercados_pct"] = (
            weekly[price_column] / weekly["precio_mercados_mediana"].replace(0, np.nan) - 1
        )
        weekly[f"disponible_{source}"] = weekly[price_column].notna()
    weekly["disponible_mercados"] = weekly["precio_mercados_mediana"].notna()
    return weekly


def _merge_optional_context(
    features: pd.DataFrame,
    production_path: Path | None,
    water_path: Path | None,
    international_features_path: Path | None = None,
) -> pd.DataFrame:
    result = features
    if production_path and production_path.exists():
        if production_path.suffix.lower() == ".csv":
            production = pd.read_csv(production_path)
        else:
            production = pd.read_excel(production_path)
        production.columns = [normalize_key(column) for column in production.columns]
        if "cultivo_canonico" in production.columns:
            production_summary = production.groupby("cultivo_canonico", as_index=False).agg(
                produccion_pronosticada=("produccion_pronosticada", "sum"),
                probabilidad_caida_10=("probabilidad_caida_10", "max"),
            )
            result = result.merge(production_summary, on="cultivo_canonico", how="left")
    if water_path and water_path.exists():
        water = pd.read_parquet(water_path)
        water["fecha"] = pd.to_datetime(water["fecha"], errors="coerce")
        national_water = (
            water.groupby("fecha", as_index=False)
            .apply(
                lambda group: pd.Series(
                    {
                        "porcentaje_agua_nacional": np.average(
                            group["porcentaje_ponderado_capacidad"].fillna(
                                group["porcentaje_promedio"]
                            ),
                            weights=group["capacidad_total_hm3"].fillna(1).clip(lower=1),
                        )
                    }
                ),
                include_groups=False,
            )
            .reset_index(drop=True)
        )
        result = pd.merge_asof(
            result.sort_values("fecha"),
            national_water.sort_values("fecha"),
            on="fecha",
            direction="backward",
            tolerance=pd.Timedelta(days=45),
        )
    if international_features_path and international_features_path.exists():
        result = _merge_international_features(result, international_features_path)
    return result


def _merge_international_features(features: pd.DataFrame, international_features_path: Path) -> pd.DataFrame:
    external = pd.read_parquet(international_features_path)
    if external.empty:
        return features
    external = external.copy()
    external["fecha_disponible"] = pd.to_datetime(
        external.get("fecha_disponible", external.get("fecha")),
        errors="coerce",
    )
    external["producto_canonico"] = external.get("producto_canonico", pd.Series(dtype=object)).map(normalize_product)
    external = external[
        external["uso_modelo"].astype(str).str.casefold().eq("feature")
        & external["fecha_disponible"].notna()
        & external["producto_canonico"].notna()
    ].copy()
    if external.empty:
        return features

    value_columns = ["valor_modelo", "cambio_1_periodo", "cambio_3_periodos", "zscore_12_periodos"]
    external = external[["fecha_disponible", "producto_canonico", "proxy_id", *value_columns]].copy()
    external["proxy_id"] = external["proxy_id"].astype(str).map(normalize_key)
    wide = external.pivot_table(
        index=["fecha_disponible", "producto_canonico"],
        columns="proxy_id",
        values=value_columns,
        aggfunc="last",
    )
    wide.columns = [
        f"{INTERNATIONAL_FEATURE_PREFIX}{proxy_id}_{metric}"
        for metric, proxy_id in wide.columns.to_flat_index()
    ]
    wide = wide.reset_index().sort_values(["producto_canonico", "fecha_disponible"])

    merged_frames: list[pd.DataFrame] = []
    base = features.copy()
    base["cultivo_canonico"] = base["cultivo_canonico"].map(normalize_product)
    for crop, group in base.groupby("cultivo_canonico", sort=False):
        context = wide[wide["producto_canonico"].eq(crop)].drop(columns=["producto_canonico"])
        if context.empty:
            merged_frames.append(group)
            continue
        merged = pd.merge_asof(
            group.sort_values("fecha"),
            context.sort_values("fecha_disponible"),
            left_on="fecha",
            right_on="fecha_disponible",
            direction="backward",
        ).drop(columns=["fecha_disponible"], errors="ignore")
        merged_frames.append(merged)
    if not merged_frames:
        return features
    return pd.concat(merged_frames, ignore_index=True, sort=False)


def build_price_product_market_features(
    wholesale: pd.DataFrame,
    spreads: pd.DataFrame,
    *,
    production_path: Path | None = None,
    water_path: Path | None = None,
    international_features_path: Path | None = None,
    horizons: tuple[int, ...] = (7, 14, 28),
) -> pd.DataFrame:
    features = _daily_market_panel(wholesale)
    features = features.merge(
        spreads,
        on=["fecha", "cultivo_canonico"],
        how="left",
    )
    group = features.groupby(["cultivo_canonico", "mercado"], sort=False)["precio_actual"]
    for lag in (1, 2, 7, 14, 28):
        features[f"precio_lag_{lag}"] = group.shift(lag)
    for window in (7, 14, 28):
        features[f"promedio_{window}"] = group.transform(
            lambda values: values.shift(1).rolling(window, min_periods=max(2, window // 3)).mean()
        )
    features["volatilidad_7"] = group.transform(
        lambda values: values.shift(1).rolling(7, min_periods=3).std()
    )
    features["volatilidad_28"] = group.transform(
        lambda values: values.shift(1).rolling(28, min_periods=7).std()
    )
    features["cambio_1"] = features["precio_actual"] / features["precio_lag_1"] - 1
    features["cambio_7"] = features["precio_actual"] / features["precio_lag_7"] - 1
    features["dia_semana"] = features["fecha"].dt.dayofweek
    features["mes"] = features["fecha"].dt.month
    day_of_year = features["fecha"].dt.dayofyear
    features["dia_anio_seno"] = np.sin(2 * np.pi * day_of_year / 365.25)
    features["dia_anio_coseno"] = np.cos(2 * np.pi * day_of_year / 365.25)
    for horizon in horizons:
        features[f"objetivo_precio_h{horizon}"] = group.shift(-horizon)
        target_change = (
            features[f"objetivo_precio_h{horizon}"] / features["precio_actual"] - 1
        )
        features[f"objetivo_alza_10_h{horizon}"] = (target_change >= 0.10).where(
            target_change.notna()
        ).astype("Int64")
        features[f"objetivo_alza_15_h{horizon}"] = (target_change >= 0.15).where(
            target_change.notna()
        ).astype("Int64")
    return _merge_optional_context(
        features,
        production_path,
        water_path,
        international_features_path,
    ).sort_values(["fecha", "cultivo_canonico", "mercado"])


def _commercial_action(probability: float, change: float) -> str:
    if probability >= 0.7 or change >= 0.15:
        return "Adelantar compras y diversificar origen."
    if probability >= 0.45 or change >= 0.08:
        return "Solicitar cotizaciones alternas y monitorear diariamente."
    return "Mantener compra normal y revisar en el siguiente corte."


def train_price_models(
    features: pd.DataFrame,
    wholesale: pd.DataFrame,
    output_dir: Path,
    *,
    horizons: tuple[int, ...] = (7, 14, 28),
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    available_features = [
        column
        for column in features.columns
        if column in MODEL_FEATURES or column.startswith(INTERNATIONAL_FEATURE_PREFIX)
    ]
    metrics: dict[str, Any] = {}
    alerts: list[pd.DataFrame] = []
    importances: list[pd.DataFrame] = []
    origin_cutoff = wholesale["fecha"].max() - pd.Timedelta(days=30)
    top_origins = (
        wholesale.loc[wholesale["fecha"] >= origin_cutoff]
        .groupby(["cultivo_canonico", "mercado", "origen"])
        .size()
        .rename("frecuencia")
        .reset_index()
        .sort_values("frecuencia", ascending=False)
        .drop_duplicates(["cultivo_canonico", "mercado"])
        .rename(columns={"origen": "origen_principal"})
    )

    for horizon in horizons:
        target = f"objetivo_precio_h{horizon}"
        training = features.dropna(subset=[target, "precio_lag_7"]).copy()
        if len(training) < 300:
            raise ValueError(
                f"No hay suficientes filas para precio h{horizon}: {len(training)}; minimo 300."
            )
        train_idx, test_idx, cutoff = temporal_train_test(training, "fecha")
        validation_features = [
            column
            for column in available_features
            if training.loc[train_idx, column].notna().any()
        ]
        model = make_regression_pipeline(training.loc[train_idx], validation_features)
        model.fit(training.loc[train_idx, validation_features], training.loc[train_idx, target])
        predicted = model.predict(training.loc[test_idx, validation_features])
        residuals = training.loc[test_idx, target].to_numpy() - predicted
        model_metrics = regression_metrics(training.loc[test_idx, target], predicted)
        autoregressive_metrics = regression_metrics(
            training.loc[test_idx, target],
            training.loc[test_idx, "precio_actual"].to_numpy(),
        )
        seasonal_metrics = regression_metrics(
            training.loc[test_idx, target],
            training.loc[test_idx, "precio_lag_7"].to_numpy(),
        )
        candidates = {
            "xgboost": model_metrics["mae"],
            "autorregresivo": autoregressive_metrics["mae"],
            "estacional_7_dias": seasonal_metrics["mae"],
        }
        operational_method = min(candidates, key=candidates.get)
        operational_validation_prediction = {
            "xgboost": predicted,
            "autorregresivo": training.loc[test_idx, "precio_actual"].to_numpy(),
            "estacional_7_dias": training.loc[test_idx, "precio_lag_7"].to_numpy(),
        }[operational_method]
        residuals = (
            training.loc[test_idx, target].to_numpy()
            - operational_validation_prediction
        )
        metrics[f"horizonte_{horizon}_dias"] = {
            "fecha_corte_validacion": cutoff.isoformat(),
            "filas_entrenamiento": int(len(train_idx)),
            "filas_validacion": int(len(test_idx)),
            "modelo_xgboost": model_metrics,
            "base_autorregresiva": autoregressive_metrics,
            "base_estacional_7_dias": seasonal_metrics,
            "metodo_operativo": operational_method,
            "xgboost_operativo": operational_method == "xgboost",
        }
        final_model = make_regression_pipeline(training, available_features)
        final_model.fit(training[available_features], training[target])
        joblib.dump(final_model, output_dir / f"modelo_precio_h{horizon}.joblib")
        latest = (
            features.dropna(subset=["precio_actual", "precio_lag_7"])
            .sort_values("fecha")
            .groupby(["cultivo_canonico", "mercado"], as_index=False)
            .tail(1)
            .copy()
        )
        latest = latest.loc[
            latest["fecha"] >= features["fecha"].max() - pd.Timedelta(days=7)
        ].copy()
        latest["precio_pronosticado"] = {
            "xgboost": final_model.predict(latest[available_features]),
            "autorregresivo": latest["precio_actual"].to_numpy(),
            "estacional_7_dias": latest["precio_lag_7"].to_numpy(),
        }[operational_method]
        latest["metodo_pronostico"] = operational_method
        latest["precio_p10"] = latest["precio_pronosticado"] + float(
            np.nanquantile(residuals, 0.10)
        )
        latest["precio_p90"] = latest["precio_pronosticado"] + float(
            np.nanquantile(residuals, 0.90)
        )
        latest["horizonte_dias"] = horizon
        latest["cambio_esperado"] = latest["precio_pronosticado"] / latest["precio_actual"] - 1
        for shock in (0.10, 0.15):
            latest[f"probabilidad_alza_{int(shock * 100)}"] = latest.apply(
                lambda row: 1
                - probability_below_from_interval(
                    float(row["precio_actual"]) * (1 + shock),
                    float(row["precio_pronosticado"]),
                    float(row["precio_p10"]),
                    float(row["precio_p90"]),
                ),
                axis=1,
            )
        latest["nivel_alerta"] = pd.cut(
            latest["probabilidad_alza_10"],
            bins=[-0.01, 0.25, 0.5, 0.75, 1],
            labels=["bajo", "medio", "alto", "critico"],
        ).astype(str)
        latest["accion_sugerida"] = latest.apply(
            lambda row: _commercial_action(
                float(row["probabilidad_alza_10"]),
                float(row["cambio_esperado"]),
            ),
            axis=1,
        )
        latest = latest.merge(
            top_origins[["cultivo_canonico", "mercado", "origen_principal"]],
            on=["cultivo_canonico", "mercado"],
            how="left",
        )
        alerts.append(latest)
        importance = model_feature_importance(final_model).head(20)
        importance["horizonte_dias"] = horizon
        importances.append(importance)
    return (
        pd.concat(alerts, ignore_index=True),
        metrics,
        pd.concat(importances, ignore_index=True),
    )


def write_price_chart(alerts: pd.DataFrame, output_path: Path) -> None:
    chart = (
        alerts.sort_values("probabilidad_alza_10", ascending=False)
        .head(15)
        .sort_values("probabilidad_alza_10")
    )
    labels = chart["cultivo_canonico"] + " | " + chart["mercado"].str.slice(0, 24)
    plt.figure(figsize=(11, 7))
    plt.barh(labels, chart["probabilidad_alza_10"], color="#b45309")
    plt.xlabel("Probabilidad de aumento mayor a 10%")
    plt.title("Principales alertas de choque de precios")
    plt.xlim(0, 1)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def write_price_horizon_charts(alerts: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for horizon in sorted(int(value) for value in alerts["horizonte_dias"].dropna().unique()):
        subset = alerts.loc[alerts["horizonte_dias"] == horizon].copy()
        if subset.empty:
            continue
        chart = (
            subset.sort_values("probabilidad_alza_10", ascending=False)
            .head(12)
            .sort_values("probabilidad_alza_10")
        )
        labels = chart["cultivo_canonico"] + " | " + chart["mercado"].str.slice(0, 24)
        plt.figure(figsize=(11, 7))
        plt.barh(labels, chart["probabilidad_alza_10"], color="#b45309")
        plt.xlabel("Probabilidad de aumento mayor a 10%")
        plt.title(f"Principales alertas de choque de precios a {horizon} dias")
        plt.xlim(0, 1)
        plt.tight_layout()
        plt.savefig(output_dir / f"principales_alertas_precios_h{horizon}.png", dpi=160)
        plt.close()


def _select_default_crop(alerts: pd.DataFrame, weekly_comparison: pd.DataFrame) -> str:
    available = sorted(weekly_comparison["cultivo_canonico"].dropna().astype(str).unique())
    if not available:
        return ""
    if alerts.empty:
        return available[0]
    longest_horizon = int(alerts["horizonte_dias"].dropna().max())
    preferred = (
        alerts.loc[alerts["horizonte_dias"] == longest_horizon]
        .sort_values("probabilidad_alza_10", ascending=False)
        .loc[:, "cultivo_canonico"]
        .dropna()
        .astype(str)
    )
    for crop in preferred:
        if crop in available:
            return crop
    return available[0]


def _write_weekly_crop_chart(crop: str, subset: pd.DataFrame, output_dir: Path) -> str:
    chart_data = subset.tail(WEEKLY_CHART_WEEKS).copy()
    filename = f"comparativo_semanal_{_slugify_filename(crop)}.png"
    output_path = output_dir / filename
    label_crop = _display_crop_name(crop)

    fig, ax = plt.subplots(figsize=(11, 5.6))
    band = chart_data["precio_mercados_min"].notna() & chart_data["precio_mercados_max"].notna()
    if band.any():
        ax.fill_between(
            chart_data.loc[band, "semana_inicio"],
            chart_data.loc[band, "precio_mercados_min"],
            chart_data.loc[band, "precio_mercados_max"],
            color="#d1fae5",
            alpha=0.9,
            label="Rango mercados SNIIM",
        )
    if chart_data["precio_mercados_mediana"].notna().any():
        ax.plot(
            chart_data["semana_inicio"],
            chart_data["precio_mercados_mediana"],
            color="#065f46",
            linewidth=2.6,
            marker="o",
            label="Mercados SNIIM",
        )
    if chart_data["precio_walmart"].notna().any():
        ax.plot(
            chart_data["semana_inicio"],
            chart_data["precio_walmart"],
            color="#b45309",
            linewidth=2.2,
            marker="o",
            label="Walmart",
        )
    if chart_data["precio_chedraui"].notna().any():
        ax.plot(
            chart_data["semana_inicio"],
            chart_data["precio_chedraui"],
            color="#be123c",
            linewidth=2.2,
            marker="o",
            label="Chedraui",
        )
    ax.set_title(f"Comparativo semanal de precios: {label_crop}")
    ax.set_ylabel("MXN por kg")
    ax.grid(axis="y", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xticks(chart_data["semana_inicio"])
    ax.set_xticklabels([value.strftime("%d/%m") for value in chart_data["semana_inicio"]], rotation=45, ha="right")
    ax.legend(loc="upper left", frameon=False, ncols=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return filename


def build_weekly_report_payload(
    weekly_comparison: pd.DataFrame,
    alerts: pd.DataFrame,
    output_dir: Path,
) -> tuple[dict[str, Any], str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    default_crop = _select_default_crop(alerts, weekly_comparison)
    crop_payloads: dict[str, Any] = {}
    for crop in sorted(weekly_comparison["cultivo_canonico"].dropna().astype(str).unique()):
        subset = (
            weekly_comparison.loc[weekly_comparison["cultivo_canonico"] == crop]
            .sort_values("semana_inicio")
            .reset_index(drop=True)
        )
        if subset.empty:
            continue
        latest = subset.iloc[-1]
        chart_file = _write_weekly_crop_chart(crop, subset, output_dir)
        week_start = pd.Timestamp(latest["semana_inicio"])
        week_end = week_start + pd.Timedelta(days=6)
        crop_payloads[crop] = {
            "crop_key": crop,
            "crop_label": _display_crop_name(crop),
            "chart_file": chart_file,
            "week_range_label": f"{week_start.strftime('%d/%m/%Y')} a {week_end.strftime('%d/%m/%Y')}",
            "cards": {
                "precio_mercados": _format_currency(latest.get("precio_mercados_mediana")),
                "precio_walmart": _format_currency(latest.get("precio_walmart")),
                "precio_chedraui": _format_currency(latest.get("precio_chedraui")),
                "cambio_mercados": _format_percent(latest.get("cambio_semanal_mercados_pct")),
                "cambio_walmart": _format_percent(latest.get("cambio_semanal_walmart_pct")),
                "cambio_chedraui": _format_percent(latest.get("cambio_semanal_chedraui_pct")),
                "spread_walmart": _format_percent(latest.get("spread_walmart_vs_mercados_pct")),
                "spread_chedraui": _format_percent(latest.get("spread_chedraui_vs_mercados_pct")),
                "mercados_cubiertos": _format_integer(latest.get("mercados_cubiertos")),
            },
            "latest": {column: _json_ready(latest.get(column)) for column in subset.columns},
        }
    payload = {
        "default_crop": default_crop,
        "crops": crop_payloads,
    }
    return payload, default_crop


def write_price_report(
    alerts: pd.DataFrame,
    anomalies: pd.DataFrame,
    weekly_comparison: pd.DataFrame,
    output_dir: Path,
    output_path: Path,
) -> None:
    weekly_payload, default_crop = build_weekly_report_payload(weekly_comparison, alerts, output_dir)
    default_meta = weekly_payload["crops"].get(default_crop, {})
    horizon_values = sorted(int(value) for value in alerts["horizonte_dias"].dropna().unique())
    default_horizon = horizon_values[0]
    sections: list[str] = []
    summary_rows = "".join(
        "<tr>"
        f"<td>{horizon}</td>"
        f"<td>{len(alerts.loc[alerts['horizonte_dias'] == horizon])}</td>"
        f"<td>{int((alerts.loc[(alerts['horizonte_dias'] == horizon) & (alerts['nivel_alerta'] == 'critico')]).shape[0])}</td>"
        f"<td>{alerts.loc[alerts['horizonte_dias'] == horizon, 'probabilidad_alza_10'].max():.1%}</td>"
        "</tr>"
        for horizon in horizon_values
    )
    for horizon in horizon_values:
        top = (
            alerts.loc[alerts["horizonte_dias"] == horizon]
            .sort_values("probabilidad_alza_10", ascending=False)
            .head(25)
        )
        rows = "".join(
            f"""<tr data-crop="{html.escape(str(row.cultivo_canonico))}">
<td>{html.escape(str(row.cultivo_canonico))}</td>
<td>{html.escape(str(row.mercado))}</td>
<td>{row.precio_actual:.2f}</td>
<td>{row.precio_pronosticado:.2f}</td>
<td>{row.probabilidad_alza_10:.1%}</td>
<td>{html.escape(str(row.metodo_pronostico))}</td>
</tr>"""
            for row in top.itertuples()
        )
        sections.append(
            f"""<section class="horizon-panel" data-horizon="{horizon}" {"hidden" if horizon != default_horizon else ""}>
<h2>Horizonte a {horizon} dias</h2>
<table><thead><tr><th>Producto</th><th>Mercado</th><th>Precio actual</th><th>Pronostico</th><th>Prob. alza &gt;10%</th><th>Metodo</th></tr></thead><tbody>{rows}</tbody></table>
<p class="empty-crop-message" hidden>No hay alertas visibles para este cultivo en este horizonte.</p>
</section>"""
        )
    anomaly_count = int((anomalies["puntaje_anomalia"].abs() >= 3).sum()) if not anomalies.empty else 0
    payload_json = json.dumps(weekly_payload, ensure_ascii=False).replace("</", "<\\/")
    output_path.write_text(
        f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Alerta temprana de precios agricolas</title><style>
body{{font-family:Arial;margin:28px;color:#17202a;background:#f8fafc}}
h1,h2{{margin:0 0 12px}}
p{{line-height:1.5}}
table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#f3f4f6}}
section{{margin:24px 0}}
.card{{background:#fff;border:1px solid #dbe4ee;border-radius:12px;padding:18px}}
.comparison-head{{display:flex;justify-content:space-between;gap:18px;align-items:end;flex-wrap:wrap;margin-bottom:16px}}
.comparison-head p{{margin:0;max-width:860px}}
.comparison-toolbar{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:18px}}
.comparison-toolbar label{{font-weight:700}}
.comparison-toolbar select{{padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;min-width:220px}}
.comparison-grid{{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:18px;align-items:start}}
.chart-frame img{{width:100%;height:auto;border-radius:10px;border:1px solid #e5e7eb;background:#fff}}
.kpi-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.kpi{{background:#f8fafc;border:1px solid #dbe4ee;border-radius:10px;padding:14px}}
.kpi-label{{display:block;font-size:12px;letter-spacing:.03em;text-transform:uppercase;color:#52606d;margin-bottom:6px}}
.kpi-value{{display:block;font-size:20px;font-weight:700;color:#17202a}}
.comparison-note{{margin-top:14px;color:#52606d;font-size:14px}}
.summary-table{{margin-top:10px}}
.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 24px}}
.toolbar button{{padding:10px 14px;border:1px solid #cbd5e1;background:#fff;border-radius:999px;cursor:pointer}}
.toolbar button.active{{background:#17202a;color:#fff;border-color:#17202a}}
.horizon-panel[hidden]{{display:none}}
.empty-crop-message{{margin:12px 0 0;color:#52606d;font-style:italic}}
@media (max-width: 980px){{.comparison-grid{{grid-template-columns:1fr}}.kpi-grid{{grid-template-columns:1fr 1fr}}}}
@media (max-width: 640px){{body{{margin:18px}}.kpi-grid{{grid-template-columns:1fr}}}}
</style></head>
<body><h1>Alerta temprana de choques de precios agricolas</h1>
<p>Se detectaron {anomaly_count} observaciones con margen retail-mayoreo atipico absoluto mayor a 3 MAD.</p>
<section class="card">
  <div class="comparison-head">
    <div>
      <h2>Comparativo semanal por cultivo</h2>
      <p>Mercados SNIIM representa la mediana semanal nacional del mayoreo. El sombreado muestra el rango semanal mediano minimo-maximo entre mercados observados.</p>
    </div>
  </div>
  <div class="comparison-toolbar">
    <label for="crop-select">Cultivo</label>
    <select id="crop-select">{"".join(f'<option value="{html.escape(crop)}" {"selected" if crop == default_crop else ""}>{html.escape(data["crop_label"])}</option>' for crop, data in weekly_payload["crops"].items())}</select>
    <strong id="week-range">{html.escape(default_meta.get("week_range_label", "s/d"))}</strong>
  </div>
  <div class="comparison-grid">
    <div class="chart-frame">
      <img id="weekly-chart" src="{html.escape(default_meta.get("chart_file", ""))}" alt="Comparativo semanal por cultivo">
    </div>
    <div class="kpi-grid">
      <div class="kpi"><span class="kpi-label">Mercados SNIIM</span><span class="kpi-value" data-card="precio_mercados">{html.escape(default_meta.get("cards", {}).get("precio_mercados", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Walmart</span><span class="kpi-value" data-card="precio_walmart">{html.escape(default_meta.get("cards", {}).get("precio_walmart", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Chedraui</span><span class="kpi-value" data-card="precio_chedraui">{html.escape(default_meta.get("cards", {}).get("precio_chedraui", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Cambio semanal mayoreo</span><span class="kpi-value" data-card="cambio_mercados">{html.escape(default_meta.get("cards", {}).get("cambio_mercados", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Cambio semanal Walmart</span><span class="kpi-value" data-card="cambio_walmart">{html.escape(default_meta.get("cards", {}).get("cambio_walmart", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Cambio semanal Chedraui</span><span class="kpi-value" data-card="cambio_chedraui">{html.escape(default_meta.get("cards", {}).get("cambio_chedraui", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Brecha Walmart vs mayoreo</span><span class="kpi-value" data-card="spread_walmart">{html.escape(default_meta.get("cards", {}).get("spread_walmart", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Brecha Chedraui vs mayoreo</span><span class="kpi-value" data-card="spread_chedraui">{html.escape(default_meta.get("cards", {}).get("spread_chedraui", "s/d"))}</span></div>
      <div class="kpi"><span class="kpi-label">Mercados cubiertos</span><span class="kpi-value" data-card="mercados_cubiertos">{html.escape(default_meta.get("cards", {}).get("mercados_cubiertos", "s/d"))}</span></div>
    </div>
  </div>
  <p class="comparison-note">Este comparativo es ejecutivo y contextual: no reemplaza la tabla de alertas por mercado, sino que resume la trayectoria semanal del cultivo para lectura rapida.</p>
</section>
<section class="summary-table">
  <h2>Resumen por horizonte</h2>
  <table><thead><tr><th>Horizonte</th><th>Alertas evaluadas</th><th>Criticas</th><th>Max prob. alza &gt;10%</th></tr></thead><tbody>{summary_rows}</tbody></table>
</section>
<div class="toolbar">{"".join(f'<button type="button" data-target="{h}" class="{"active" if h == default_horizon else ""}">{h} dias</button>' for h in horizon_values)}</div>
{"".join(sections)}
<script id="weekly-comparison-data" type="application/json">{payload_json}</script>
<script>
const weeklyPayload = JSON.parse(document.getElementById('weekly-comparison-data').textContent);
const cropSelect = document.getElementById('crop-select');
const weekRange = document.getElementById('week-range');
const weeklyChart = document.getElementById('weekly-chart');
const weeklyCards = document.querySelectorAll('[data-card]');
function filterTablesByCrop(cropKey) {{
  document.querySelectorAll('.horizon-panel').forEach(panel => {{
    let visibleRows = 0;
    panel.querySelectorAll('tbody tr[data-crop]').forEach(row => {{
      const visible = row.dataset.crop === cropKey;
      row.hidden = !visible;
      if (visible) visibleRows += 1;
    }});
    const emptyMessage = panel.querySelector('.empty-crop-message');
    if (emptyMessage) {{
      emptyMessage.hidden = visibleRows !== 0;
    }}
  }});
}}
function renderCrop(cropKey) {{
  const meta = weeklyPayload.crops[cropKey];
  if (!meta) return;
  weekRange.textContent = meta.week_range_label || 's/d';
  weeklyChart.src = meta.chart_file || '';
  weeklyChart.alt = `Comparativo semanal de precios para ${{meta.crop_label || cropKey}}`;
  weeklyCards.forEach(node => {{
    const key = node.dataset.card;
    node.textContent = (meta.cards && meta.cards[key]) || 's/d';
  }});
  filterTablesByCrop(cropKey);
}}
cropSelect?.addEventListener('change', event => renderCrop(event.target.value));
renderCrop(weeklyPayload.default_crop || cropSelect?.value);
document.querySelectorAll('.toolbar button').forEach(button => {{
  button.addEventListener('click', () => {{
    const target = button.dataset.target;
    document.querySelectorAll('.toolbar button').forEach(node => node.classList.toggle('active', node === button));
    document.querySelectorAll('.horizon-panel').forEach(panel => {{
      panel.hidden = panel.dataset.horizon !== target;
    }});
  }});
}});
</script>
</body></html>""",
        encoding="utf-8",
    )


def run_price_shock_pipeline(
    daily_root: Path,
    output_dir: Path,
    *,
    production_path: Path | None = None,
    water_path: Path | None = None,
    international_features_path: Path | None = None,
    horizons: tuple[int, ...] = (7, 14, 28),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    wholesale = load_sniim_daily_history(daily_root)
    spreads = build_retail_spreads(daily_root, wholesale)
    anomalies = build_margin_anomalies(spreads)
    weekly_comparison = build_weekly_price_comparison(wholesale, spreads)
    features = build_price_product_market_features(
        wholesale,
        spreads,
        production_path=production_path,
        water_path=water_path,
        international_features_path=international_features_path,
        horizons=horizons,
    )
    generated_at = datetime.now().isoformat(timespec="seconds")
    write_parquet_with_metadata(
        features,
        output_dir / "price_product_market_daily_features.parquet",
        metadata={
            "generado_en": generated_at,
            "raiz_corridas_diarias": str(daily_root),
            "fecha_minima": features["fecha"].min(),
            "fecha_maxima": features["fecha"].max(),
            "productos": int(features["cultivo_canonico"].nunique()),
            "mercados": int(features["mercado"].nunique()),
            "archivo_produccion": str(production_path) if production_path else None,
            "archivo_agua": str(water_path) if water_path else None,
            "archivo_precios_internacionales": (
                str(international_features_path) if international_features_path else None
            ),
        },
    )
    alerts, metrics, importance = train_price_models(
        features,
        wholesale,
        output_dir,
        horizons=horizons,
    )
    alerts.to_csv(output_dir / "alertas_semanales_precios.csv", index=False, encoding="utf-8-sig")
    anomalies.to_csv(output_dir / "anomalias_margen_retail.csv", index=False, encoding="utf-8-sig")
    weekly_comparison.to_csv(output_dir / "comparativo_precios_semanales.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_dir / "alerta_temprana_precios.xlsx", engine="openpyxl") as writer:
        alerts.to_excel(writer, sheet_name="alertas", index=False)
        (
            alerts.groupby("horizonte_dias", as_index=False)
            .agg(
                alertas=("cultivo_canonico", "size"),
                alertas_criticas=("nivel_alerta", lambda values: int((values == "critico").sum())),
                max_probabilidad_alza_10=("probabilidad_alza_10", "max"),
            )
            .sort_values("horizonte_dias")
        ).to_excel(writer, sheet_name="resumen_horizontes", index=False)
        weekly_comparison.to_excel(writer, sheet_name="comparativo_semanal", index=False)
        anomalies.to_excel(writer, sheet_name="anomalias_margen", index=False)
        importance.to_excel(writer, sheet_name="explicabilidad", index=False)
        pd.DataFrame(
            [{"metrica": key, "valor": json.dumps(value, ensure_ascii=False)} for key, value in metrics.items()]
        ).to_excel(writer, sheet_name="validacion", index=False)
    (output_dir / "metricas_modelo_precios.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_price_chart(alerts, output_dir / "principales_alertas_precios.png")
    write_price_horizon_charts(alerts, output_dir)
    write_price_report(
        alerts,
        anomalies,
        weekly_comparison,
        output_dir,
        output_dir / "reporte_alertas_precios.html",
    )
    return {
        "filas_features": len(features),
        "alertas": len(alerts),
        "anomalias_margen": len(anomalies),
        "filas_comparativo_semanal": len(weekly_comparison),
        "metricas": metrics,
    }
