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
    retail["precio"] = pd.to_numeric(retail.get("precio_kg_mxn"), errors="coerce").combine_first(
        pd.to_numeric(retail.get("precio_mxn"), errors="coerce")
    )
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
    for source in ("walmart", "chedraui"):
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
    for source in ("walmart", "chedraui"):
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
            top_origins[
                ["cultivo_canonico", "mercado", "origen_principal"]
            ],
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


def write_price_report(alerts: pd.DataFrame, anomalies: pd.DataFrame, output_path: Path) -> None:
    top = alerts.sort_values("probabilidad_alza_10", ascending=False).head(40)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.cultivo_canonico))}</td>"
        f"<td>{html.escape(str(row.mercado))}</td>"
        f"<td>{int(row.horizonte_dias)}</td>"
        f"<td>{row.precio_actual:.2f}</td><td>{row.precio_pronosticado:.2f}</td>"
        f"<td>{row.probabilidad_alza_10:.1%}</td>"
        f"<td>{html.escape(str(row.accion_sugerida))}</td></tr>"
        for row in top.itertuples()
    )
    anomaly_count = int((anomalies["puntaje_anomalia"].abs() >= 3).sum()) if not anomalies.empty else 0
    output_path.write_text(
        f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Alerta temprana de precios agricolas</title><style>
body{{font-family:Arial;margin:28px;color:#17202a}}table{{border-collapse:collapse;width:100%}}
th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#f3f4f6}}</style></head>
<body><h1>Alerta temprana de choques de precios agricolas</h1>
<p>Se detectaron {anomaly_count} observaciones con margen retail-mayoreo atipico absoluto mayor a 3 MAD.</p>
<table><thead><tr><th>Producto</th><th>Mercado</th><th>Horizonte</th><th>Precio actual</th>
<th>Pronostico</th><th>Prob. alza &gt;10%</th><th>Accion</th></tr></thead><tbody>{rows}</tbody></table>
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
    wholesale = load_sniim_daily_history(daily_root)
    spreads = build_retail_spreads(daily_root, wholesale)
    anomalies = build_margin_anomalies(spreads)
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
    with pd.ExcelWriter(output_dir / "alerta_temprana_precios.xlsx", engine="openpyxl") as writer:
        alerts.to_excel(writer, sheet_name="alertas", index=False)
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
    write_price_report(alerts, anomalies, output_dir / "reporte_alertas_precios.html")
    return {
        "filas_features": len(features),
        "alertas": len(alerts),
        "anomalias_margen": len(anomalies),
        "metricas": metrics,
    }
