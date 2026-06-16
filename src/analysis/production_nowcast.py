from __future__ import annotations

import html
import json
import re
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
    probability_shortfall_from_interval,
    read_sheet_aliases,
    regression_metrics,
    temporal_train_test,
    write_parquet_with_metadata,
)

AVANCE_COLUMN_MAP = {
    "entidad": "estado",
    "entidad_entidad": "estado",
    "superficie_sembrada_ha": "superficie_sembrada_ha",
    "superficie_cosechada_ha": "superficie_cosechada_ha",
    "superficie_siniestrada_ha": "superficie_siniestrada_ha",
    "produccion": "produccion_acumulada",
    "produccion_produccion": "produccion_acumulada",
    "rendimiento_udm_ha": "rendimiento_actual",
    "rendimiento_udm_ha_rendimiento_udm_ha": "rendimiento_actual",
    "cultivo_avance_agricola": "cultivo",
    "avance_crop_name": "cultivo",
    "cultivo_avance_agricola_original": "cultivo_original",
    "unidad_avance_agricola": "unidad",
    "anio_consulta": "anio",
    "query_year": "anio",
    "mes_consulta": "mes_corte",
    "query_month": "mes_corte",
    "mes_consulta_nombre": "mes_corte_nombre",
    "situacion_corte": "situacion_corte",
}

CIERRE_COLUMN_MAP = {
    "entidad": "estado",
    "entidad_entidad": "estado",
    "superficie_sembrada_ha": "superficie_sembrada_final_ha",
    "superficie_cosechada_ha": "superficie_cosechada_final_ha",
    "superficie_siniestrada_ha": "superficie_siniestrada_final_ha",
    "produccion": "produccion_final",
    "produccion_produccion": "produccion_final",
    "rendimiento_udm_ha": "rendimiento_final",
    "rendimiento_udm_ha_rendimiento_udm_ha": "rendimiento_final",
    "pmr_mxn_udm": "pmr_final",
    "pmr_udm_pmr_udm": "pmr_final",
    "cultivo_cierre_agricola": "cultivo",
    "cierre_crop_name": "cultivo",
    "cultivo_cierre_agricola_original": "cultivo_original",
    "unidad_cierre_agricola": "unidad",
    "anio_consulta": "anio",
    "query_year": "anio",
}

MODEL_FEATURES = [
    "superficie_sembrada_ha",
    "superficie_cosechada_ha",
    "superficie_siniestrada_ha",
    "produccion_acumulada",
    "rendimiento_actual",
    "avance_cosecha",
    "proporcion_siniestrada",
    "mes_corte",
    "produccion_anio_anterior",
    "produccion_promedio_5_anios",
    "rendimiento_anio_anterior",
    "porcentaje_ponderado_capacidad",
    "porcentaje_promedio",
    "presas_bajo_40",
    "cultivo_canonico",
    "estado",
]


def _canonical_from_path(path: Path) -> str:
    stem = re.sub(r"_(?:19|20)\d{2}.*$", "", path.stem)
    return normalize_key(stem)


def _read_agricultural_files(root: Path, column_map: dict[str, str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(root.rglob("*.xlsx")):
        try:
            frame = read_sheet_aliases(path, ("datos", "data", "Sheet1"), fallback_first=True)
        except Exception:
            continue
        if frame.empty:
            continue
        normalized = frame.rename(
            columns={
                column: column_map.get(normalize_key(column), normalize_key(column))
                for column in frame.columns
            }
        )
        normalized["archivo_fuente"] = str(path)
        if "cultivo" not in normalized.columns:
            normalized["cultivo"] = _canonical_from_path(path)
        normalized["cultivo_canonico"] = normalized["cultivo"].map(normalize_product)
        missing_crop = normalized["cultivo_canonico"].eq("")
        normalized.loc[missing_crop, "cultivo_canonico"] = normalize_product(
            _canonical_from_path(path)
        )
        normalized["estado"] = normalized.get("estado", pd.Series(dtype="object")).astype(str).str.strip()
        frames.append(normalized)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def load_avance_history(root: Path) -> pd.DataFrame:
    avance = _read_agricultural_files(root, AVANCE_COLUMN_MAP)
    if avance.empty:
        raise ValueError(f"No se encontraron exportes de Avance Agricola en {root}")
    for column in (
        "anio",
        "mes_corte",
        "superficie_sembrada_ha",
        "superficie_cosechada_ha",
        "superficie_siniestrada_ha",
        "produccion_acumulada",
        "rendimiento_actual",
    ):
        avance[column] = pd.to_numeric(avance.get(column), errors="coerce")
    avance["fecha_corte"] = pd.to_datetime(
        {
            "year": avance["anio"],
            "month": avance["mes_corte"],
            "day": 1,
        },
        errors="coerce",
    ) + pd.offsets.MonthEnd(0)
    keys = ["cultivo_canonico", "estado", "anio", "mes_corte"]
    return avance.sort_values("archivo_fuente").drop_duplicates(keys, keep="last")


def load_cierre_history(root: Path) -> pd.DataFrame:
    cierre = _read_agricultural_files(root, CIERRE_COLUMN_MAP)
    if cierre.empty:
        raise ValueError(f"No se encontraron exportes de Cierre Agricola en {root}")
    for column in (
        "anio",
        "produccion_final",
        "rendimiento_final",
        "superficie_sembrada_final_ha",
        "superficie_cosechada_final_ha",
        "superficie_siniestrada_final_ha",
        "pmr_final",
    ):
        cierre[column] = pd.to_numeric(cierre.get(column), errors="coerce")
    keys = ["cultivo_canonico", "estado", "anio"]
    return cierre.sort_values("archivo_fuente").drop_duplicates(keys, keep="last")


def _historical_references(cierre: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (crop, state), group in cierre.groupby(["cultivo_canonico", "estado"], dropna=False):
        ordered = group.sort_values("anio")
        for _, row in ordered.iterrows():
            previous = ordered.loc[ordered["anio"] == row["anio"] - 1]
            history = ordered.loc[
                (ordered["anio"] < row["anio"]) & (ordered["anio"] >= row["anio"] - 5)
            ]
            rows.append(
                {
                    "cultivo_canonico": crop,
                    "estado": state,
                    "anio": row["anio"],
                    "produccion_anio_anterior": (
                        previous["produccion_final"].iloc[-1] if not previous.empty else np.nan
                    ),
                    "rendimiento_anio_anterior": (
                        previous["rendimiento_final"].iloc[-1] if not previous.empty else np.nan
                    ),
                    "produccion_promedio_5_anios": history["produccion_final"].mean(),
                    "desviacion_produccion_5_anios": history["produccion_final"].std(),
                }
            )
    return pd.DataFrame(rows)


def _current_references(avance: pd.DataFrame, cierre: pd.DataFrame) -> pd.DataFrame:
    keys = avance[["cultivo_canonico", "estado", "anio"]].drop_duplicates()
    rows: list[dict[str, Any]] = []
    for _, key in keys.iterrows():
        history = cierre.loc[
            (cierre["cultivo_canonico"] == key["cultivo_canonico"])
            & (cierre["estado"] == key["estado"])
            & (cierre["anio"] < key["anio"])
        ].sort_values("anio")
        recent = history.tail(5)
        previous = history.loc[history["anio"] == key["anio"] - 1]
        rows.append(
            {
                **key.to_dict(),
                "produccion_anio_anterior": (
                    previous["produccion_final"].iloc[-1] if not previous.empty else np.nan
                ),
                "rendimiento_anio_anterior": (
                    previous["rendimiento_final"].iloc[-1] if not previous.empty else np.nan
                ),
                "produccion_promedio_5_anios": recent["produccion_final"].mean(),
                "desviacion_produccion_5_anios": recent["produccion_final"].std(),
            }
        )
    return pd.DataFrame(rows)


def _merge_water(features: pd.DataFrame, water_path: Path | None) -> pd.DataFrame:
    if water_path is None or not water_path.exists():
        return features
    water = pd.read_parquet(water_path)
    water["fecha"] = pd.to_datetime(water["fecha"], errors="coerce")
    left = features.sort_values(["fecha_corte", "estado"])
    right = water.sort_values(["fecha", "estado"])
    return pd.merge_asof(
        left,
        right,
        left_on="fecha_corte",
        right_on="fecha",
        by="estado",
        direction="backward",
        tolerance=pd.Timedelta(days=45),
    )


def build_crop_state_cutoff_features(
    avance: pd.DataFrame,
    cierre: pd.DataFrame,
    *,
    water_path: Path | None = None,
) -> pd.DataFrame:
    features = avance.copy()
    references = _current_references(features, cierre)
    features = features.merge(
        references,
        on=["cultivo_canonico", "estado", "anio"],
        how="left",
    )
    final_targets = cierre[
        [
            "cultivo_canonico",
            "estado",
            "anio",
            "produccion_final",
            "rendimiento_final",
        ]
    ]
    features = features.merge(
        final_targets,
        on=["cultivo_canonico", "estado", "anio"],
        how="left",
    )
    planted = features["superficie_sembrada_ha"].where(
        features["superficie_sembrada_ha"] > 0
    )
    features["avance_cosecha"] = features["superficie_cosechada_ha"] / planted
    features["proporcion_siniestrada"] = features["superficie_siniestrada_ha"] / planted
    features["avance_produccion_vs_anio_anterior"] = (
        features["produccion_acumulada"] / features["produccion_anio_anterior"].replace(0, np.nan)
    )
    features = _merge_water(features, water_path)
    return features.sort_values(
        ["fecha_corte", "cultivo_canonico", "estado"]
    ).reset_index(drop=True)


def _baseline_forecast(frame: pd.DataFrame) -> pd.Series:
    baseline = frame[
        [
            "produccion_anio_anterior",
            "produccion_promedio_5_anios",
            "produccion_acumulada",
    ]
    ].bfill(axis=1).iloc[:, 0]
    return pd.concat([baseline, frame["produccion_acumulada"]], axis=1).max(axis=1)


def _pct_change(current: pd.Series, reference: pd.Series) -> pd.Series:
    return current / reference.replace(0, np.nan) - 1


def _add_comparison_columns(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["referencia_comparacion"] = enriched["produccion_anio_anterior"].where(
        enriched["produccion_anio_anterior"].notna(),
        enriched["produccion_promedio_5_anios"],
    )
    enriched["tipo_referencia_comparacion"] = np.select(
        [
            enriched["produccion_anio_anterior"].notna(),
            enriched["produccion_promedio_5_anios"].notna(),
        ],
        [
            "anio_anterior",
            "promedio_5_anios",
        ],
        default="sin_referencia",
    )
    enriched["cambio_abs_vs_referencia"] = (
        enriched["produccion_pronosticada"] - enriched["referencia_comparacion"]
    )
    enriched["cambio_pct_vs_referencia"] = _pct_change(
        enriched["produccion_pronosticada"], enriched["referencia_comparacion"]
    )
    return enriched


def _format_number(value: Any) -> str:
    if pd.isna(value):
        return "s/d"
    return f"{float(value):.0f}"


def _format_percent(value: Any, *, signed: bool = False) -> str:
    if pd.isna(value):
        return "s/d"
    pattern = "+.1%" if signed else ".1%"
    return format(float(value), pattern)


def _comparison_label(value: Any) -> str:
    labels = {
        "anio_anterior": "Anio anterior",
        "promedio_5_anios": "Promedio 5 anios",
    }
    return labels.get(str(value), "Sin referencia")


def _build_summary(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    summary = (
        frame.groupby(group_column, as_index=False)
        .agg(
            produccion_pronosticada=("produccion_pronosticada", "sum"),
            referencia_comparacion=("referencia_comparacion", lambda values: values.sum(min_count=1)),
            produccion_anio_anterior=("produccion_anio_anterior", lambda values: values.sum(min_count=1)),
            produccion_promedio_5_anios=("produccion_promedio_5_anios", lambda values: values.sum(min_count=1)),
            produccion_p10=("produccion_p10", "sum"),
            produccion_p90=("produccion_p90", "sum"),
            probabilidad_caida_10=("probabilidad_caida_10", "max"),
            alertas_altas_o_criticas=("nivel_riesgo", lambda values: int(values.isin(["alto", "critico"]).sum())),
        )
    )
    summary["cambio_pct_vs_referencia"] = _pct_change(
        summary["produccion_pronosticada"], summary["referencia_comparacion"]
    )
    summary["cambio_pct_vs_anio_anterior"] = _pct_change(
        summary["produccion_pronosticada"], summary["produccion_anio_anterior"]
    )
    summary["cambio_pct_vs_promedio_5_anios"] = _pct_change(
        summary["produccion_pronosticada"], summary["produccion_promedio_5_anios"]
    )
    return summary.sort_values("produccion_pronosticada", ascending=False)


def train_and_forecast_production(
    features: pd.DataFrame,
    output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_columns = [column for column in MODEL_FEATURES if column in features.columns]
    training = features.dropna(subset=["produccion_final"]).copy()
    years = training["anio"].dropna().nunique()
    current = (
        features.sort_values("fecha_corte")
        .groupby(["cultivo_canonico", "estado", "anio"], as_index=False)
        .tail(1)
        .copy()
    )
    current["anio_objetivo"] = current["anio"]
    current["horizonte_pronostico"] = "cierre_agricola_anual_del_mismo_anio"
    current["descripcion_horizonte"] = (
        "Pronostico de la produccion final del mismo anio agricola, no de los proximos dias o semanas."
    )
    metrics: dict[str, Any] = {
        "modo": "base_historica",
        "filas_etiquetadas": int(len(training)),
        "anios_etiquetados": int(years),
    }
    importance = pd.DataFrame(columns=["variable", "importancia"])

    if len(training) >= 100 and years >= 2:
        train_idx, test_idx, cutoff = temporal_train_test(training, "fecha_corte")
        model = make_regression_pipeline(training, feature_columns)
        model.fit(training.loc[train_idx, feature_columns], training.loc[train_idx, "produccion_final"])
        predictions = model.predict(training.loc[test_idx, feature_columns])
        baseline = _baseline_forecast(training.loc[test_idx])
        residuals = training.loc[test_idx, "produccion_final"].to_numpy() - predictions
        metrics = {
            "modo": "xgboost",
            "fecha_corte_validacion": cutoff.isoformat(),
            "filas_entrenamiento": int(len(train_idx)),
            "filas_validacion": int(len(test_idx)),
            "modelo_xgboost": regression_metrics(
                training.loc[test_idx, "produccion_final"], predictions
            ),
            "base_historica": regression_metrics(
                training.loc[test_idx, "produccion_final"], baseline.to_numpy()
            ),
        }
        final_model = make_regression_pipeline(training, feature_columns)
        final_model.fit(training[feature_columns], training["produccion_final"])
        joblib.dump(final_model, output_dir / "modelo_nowcast_produccion.joblib")
        current["produccion_pronosticada"] = final_model.predict(current[feature_columns])
        lower_residual = float(np.nanquantile(residuals, 0.10))
        upper_residual = float(np.nanquantile(residuals, 0.90))
        current["produccion_p10"] = current["produccion_pronosticada"] + lower_residual
        current["produccion_p90"] = current["produccion_pronosticada"] + upper_residual
        importance = model_feature_importance(final_model).head(30)
    else:
        current["produccion_pronosticada"] = _baseline_forecast(current)
        historical_std = current["desviacion_produccion_5_anios"].fillna(
            current["produccion_pronosticada"].abs() * 0.15
        )
        current["produccion_p10"] = current["produccion_pronosticada"] - 1.2816 * historical_std
        current["produccion_p90"] = current["produccion_pronosticada"] + 1.2816 * historical_std
        metrics["motivo"] = (
            "Se requieren al menos 100 cortes historicos etiquetados y dos anios. "
            "No se entreno un modelo para evitar resultados no defendibles."
        )

    current["cambio_vs_anio_anterior"] = _pct_change(
        current["produccion_pronosticada"], current["produccion_anio_anterior"]
    )
    current["cambio_vs_promedio_5_anios"] = _pct_change(
        current["produccion_pronosticada"], current["produccion_promedio_5_anios"]
    )
    for shortfall in (0.10, 0.15, 0.20):
        current[f"probabilidad_caida_{int(shortfall * 100)}"] = current.apply(
            lambda row: (
                probability_shortfall_from_interval(
                    float(row["produccion_anio_anterior"]),
                    shortfall,
                    float(row["produccion_pronosticada"]),
                    float(row["produccion_p10"]),
                    float(row["produccion_p90"]),
                )
                if pd.notna(row["produccion_anio_anterior"])
                else np.nan
            ),
            axis=1,
        )
    current["escenario_normal"] = current["produccion_pronosticada"]
    current["escenario_seco"] = current["produccion_pronosticada"] * 0.92
    current["escenario_sequia_severa"] = current["produccion_pronosticada"] * 0.85
    current["supuesto_escenarios"] = (
        "Normal=0%; seco=-8%; sequia severa=-15% sobre el pronostico central."
    )
    current = _add_comparison_columns(current)
    current["nivel_riesgo"] = pd.cut(
        current["probabilidad_caida_10"].fillna(0),
        bins=[-0.01, 0.25, 0.5, 0.75, 1.0],
        labels=["bajo", "medio", "alto", "critico"],
    ).astype(str)
    return current, metrics, importance


def write_production_chart(forecast: pd.DataFrame, output_path: Path) -> None:
    chart = (
        forecast.sort_values("probabilidad_caida_10", ascending=False)
        .head(12)
        .sort_values("probabilidad_caida_10")
    )
    labels = chart["cultivo_canonico"] + " | " + chart["estado"].str.slice(0, 20)
    plt.figure(figsize=(11, 7))
    plt.barh(labels, chart["probabilidad_caida_10"].fillna(0), color="#0f766e")
    plt.xlabel("Probabilidad de caida mayor a 10%")
    plt.title("Principales riesgos de produccion")
    plt.xlim(0, 1)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def write_production_report(forecast: pd.DataFrame, metrics: dict[str, Any], output_path: Path) -> None:
    top_risk = forecast.sort_values(
        ["probabilidad_caida_10", "cambio_pct_vs_referencia"],
        ascending=[False, True],
        na_position="last",
    ).head(20)
    largest_volume = forecast.sort_values("produccion_pronosticada", ascending=False).head(20)
    risk_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.cultivo_canonico))}</td>"
        f"<td>{html.escape(str(row.estado))}</td>"
        f"<td>{_format_number(row.produccion_pronosticada)}</td>"
        f"<td>{_comparison_label(row.tipo_referencia_comparacion)}</td>"
        f"<td>{_format_number(row.referencia_comparacion)}</td>"
        f"<td>{_format_percent(row.cambio_pct_vs_referencia, signed=True)}</td>"
        f"<td>{_format_percent(row.probabilidad_caida_10)}</td>"
        f"<td>{html.escape(str(row.nivel_riesgo))}</td>"
        "</tr>"
        for row in top_risk.itertuples()
    )
    volume_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.cultivo_canonico))}</td>"
        f"<td>{html.escape(str(row.estado))}</td>"
        f"<td>{_format_number(row.produccion_pronosticada)}</td>"
        f"<td>{_comparison_label(row.tipo_referencia_comparacion)}</td>"
        f"<td>{_format_percent(row.cambio_pct_vs_referencia, signed=True)}</td>"
        f"<td>{_format_number(row.produccion_p10)}</td>"
        f"<td>{_format_number(row.produccion_p90)}</td>"
        f"<td>{html.escape(str(row.nivel_riesgo))}</td>"
        "</tr>"
        for row in largest_volume.itertuples()
    )
    output_path.write_text(
        f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Nowcast de produccion agricola</title><style>
body{{font-family:Arial;margin:28px;color:#17202a}}table{{border-collapse:collapse;width:100%;margin-top:18px}}
th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#f3f4f6}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:20px 0}}
.kpi{{border:1px solid #dbe4ea;border-radius:8px;padding:16px;background:#fff}}
</style></head><body>
<h1>Nowcast de produccion agricola</h1>
<p>Modo actual: <strong>{html.escape(str(metrics.get("modo", "")))}</strong>. Esta vista resume volumen esperado y focos de riesgo para presentacion ejecutiva.</p>
<p><strong>Horizonte del pronostico:</strong> produccion final del mismo anio agricola para cada cultivo-estado, usando el ultimo corte mensual disponible. No es un pronostico a 7, 14 o 30 dias.</p>
<p><strong>Como leer la caida esperada:</strong> la comparacion usa primero el anio anterior y, si no existe, cae al promedio de los ultimos 5 anios. Cuando no hay base suficiente se muestra <strong>s/d</strong>.</p>
<div class="grid">
<div class="kpi"><strong>Pronosticos</strong><br>{len(forecast)}</div>
<div class="kpi"><strong>Cultivos</strong><br>{forecast['cultivo_canonico'].nunique()}</div>
<div class="kpi"><strong>Estados</strong><br>{forecast['estado'].nunique()}</div>
<div class="kpi"><strong>Alertas altas o criticas</strong><br>{int(forecast['nivel_riesgo'].isin(['alto','critico']).sum())}</div>
</div>
<h2>Mayores riesgos de caida</h2>
<table><thead><tr><th>Cultivo</th><th>Estado</th><th>Produccion pronosticada</th><th>Base de comparacion</th><th>Produccion de referencia</th><th>Variacion esperada</th><th>Prob. caida &gt;10% vs anio anterior</th><th>Riesgo</th></tr></thead><tbody>{risk_rows}</tbody></table>
<h2>Mayores volumenes pronosticados</h2>
<table><thead><tr><th>Cultivo</th><th>Estado</th><th>Pronostico</th><th>Base de comparacion</th><th>Variacion esperada</th><th>P10</th><th>P90</th><th>Riesgo</th></tr></thead><tbody>{volume_rows}</tbody></table>
</body></html>""",
        encoding="utf-8",
    )


def run_production_nowcast_pipeline(
    avance_root: Path,
    cierre_root: Path,
    output_dir: Path,
    *,
    water_path: Path | None = None,
) -> dict[str, Any]:
    avance = load_avance_history(avance_root)
    cierre = load_cierre_history(cierre_root)
    features = build_crop_state_cutoff_features(avance, cierre, water_path=water_path)
    generated_at = datetime.now().isoformat(timespec="seconds")
    write_parquet_with_metadata(
        features,
        output_dir / "crop_state_cutoff_features.parquet",
        metadata={
            "generado_en": generated_at,
            "raiz_avance": str(avance_root),
            "raiz_cierre": str(cierre_root),
            "archivo_riesgo_hidrico": str(water_path) if water_path else None,
            "filas": len(features),
            "filas_con_objetivo": int(features["produccion_final"].notna().sum()),
        },
    )
    forecast, metrics, importance = train_and_forecast_production(features, output_dir)
    forecast.to_csv(
        output_dir / "pronostico_produccion_mensual.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with pd.ExcelWriter(output_dir / "nowcast_produccion_agricola.xlsx", engine="openpyxl") as writer:
        forecast.to_excel(writer, sheet_name="pronostico", index=False)
        _build_summary(forecast, "cultivo_canonico").to_excel(writer, sheet_name="resumen_cultivo", index=False)
        _build_summary(forecast, "estado").to_excel(writer, sheet_name="resumen_estado", index=False)
        forecast.pivot_table(
            index="estado",
            columns="cultivo_canonico",
            values="probabilidad_caida_10",
            aggfunc="max",
        ).to_excel(writer, sheet_name="matriz_riesgo")
        forecast[
            [
                "cultivo_canonico",
                "estado",
                "escenario_normal",
                "escenario_seco",
                "escenario_sequia_severa",
                "supuesto_escenarios",
            ]
        ].to_excel(writer, sheet_name="escenarios", index=False)
        importance.to_excel(writer, sheet_name="explicabilidad", index=False)
        pd.DataFrame(
            [{"metrica": key, "valor": json.dumps(value, ensure_ascii=False)} for key, value in metrics.items()]
        ).to_excel(writer, sheet_name="validacion", index=False)
    (output_dir / "metricas_nowcast_produccion.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_production_chart(forecast, output_dir / "principales_riesgos_produccion.png")
    write_production_report(forecast, metrics, output_dir / "reporte_nowcast_produccion.html")
    return {
        "filas_features": len(features),
        "pronosticos": len(forecast),
        "modo": metrics["modo"],
        "metricas": metrics,
    }
