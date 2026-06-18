import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.analysis.production_nowcast import (
    build_crop_state_cutoff_features,
    train_and_forecast_production,
    write_production_report,
)


class ProductionNowcastTests(unittest.TestCase):
    def test_builds_leakage_safe_references_and_baseline(self) -> None:
        avance = pd.DataFrame(
            [
                {
                    "cultivo_canonico": "aguacate",
                    "estado": "Michoacan",
                    "anio": 2025,
                    "mes_corte": 5,
                    "fecha_corte": pd.Timestamp("2025-05-31"),
                    "superficie_sembrada_ha": 100,
                    "superficie_cosechada_ha": 50,
                    "superficie_siniestrada_ha": 5,
                    "produccion_acumulada": 70,
                    "rendimiento_actual": 1.4,
                }
            ]
        )
        cierre = pd.DataFrame(
            [
                {
                    "cultivo_canonico": "aguacate",
                    "estado": "Michoacan",
                    "anio": 2024,
                    "produccion_final": 120,
                    "rendimiento_final": 1.8,
                }
            ]
        )
        features = build_crop_state_cutoff_features(avance, cierre)
        self.assertEqual(float(features.iloc[0]["produccion_anio_anterior"]), 120)
        self.assertTrue(pd.isna(features.iloc[0]["produccion_final"]))

        with tempfile.TemporaryDirectory() as temp_dir:
            forecast, metrics, _ = train_and_forecast_production(features, Path(temp_dir))
        self.assertEqual(metrics["modo"], "base_historica")
        self.assertEqual(float(forecast.iloc[0]["produccion_pronosticada"]), 120)
        self.assertEqual(str(forecast.iloc[0]["tipo_referencia_comparacion"]), "anio_anterior")
        self.assertEqual(float(forecast.iloc[0]["referencia_comparacion"]), 120)
        self.assertEqual(float(forecast.iloc[0]["cambio_pct_vs_referencia"]), 0.0)
        self.assertEqual(str(forecast.iloc[0]["horizonte_pronostico"]), "cierre_agricola_anual_del_mismo_anio")
        self.assertEqual(int(forecast.iloc[0]["anio_objetivo"]), 2025)

    def test_production_report_is_visual_and_summary_oriented(self) -> None:
        forecast = pd.DataFrame(
            [
                {
                    "cultivo_canonico": "aguacate",
                    "estado": "Michoacan",
                    "produccion_pronosticada": 120.0,
                    "produccion_p10": 100.0,
                    "produccion_p90": 140.0,
                    "referencia_comparacion": 150.0,
                    "tipo_referencia_comparacion": "anio_anterior",
                    "cambio_pct_vs_referencia": -0.2,
                    "probabilidad_caida_10": 0.6,
                    "nivel_riesgo": "alto",
                }
            ]
        )
        metrics = {"modo": "base_historica"}
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.html"
            write_production_report(forecast, metrics, output)
            html = output.read_text(encoding="utf-8")

        self.assertIn("Nowcast de produccion agricola", html)
        self.assertIn("Mayores riesgos de caida", html)
        self.assertIn("Mayores volumenes pronosticados", html)
        self.assertIn("Horizonte del pronostico", html)
        self.assertIn("Base de comparacion", html)
        self.assertIn("Variacion esperada", html)
        self.assertIn("-20.0%", html)
        self.assertIn("60.0%", html)
        self.assertIn("Metodo forzado", html)
        self.assertNotIn("nan%", html)

    def test_uses_baseline_when_xgboost_loses_validation(self) -> None:
        class FakeModel:
            def fit(self, *_args, **_kwargs):
                return self

            def predict(self, features):
                return pd.Series([0.0] * len(features)).to_numpy()

        rows = []
        for year in (2023, 2024):
            for month in range(1, 7):
                for state in ("Michoacan", "Jalisco", "Puebla", "Nayarit", "Colima", "Morelos", "Oaxaca", "Chiapas", "Guerrero", "Veracruz"):
                    rows.append(
                        {
                            "cultivo_canonico": "aguacate",
                            "estado": state,
                            "anio": year,
                            "mes_corte": month,
                            "fecha_corte": pd.Timestamp(year=year, month=month, day=28) + pd.offsets.MonthEnd(0),
                            "superficie_sembrada_ha": 100.0,
                            "superficie_cosechada_ha": 60.0,
                            "superficie_siniestrada_ha": 5.0,
                            "produccion_acumulada": 100.0,
                            "rendimiento_actual": 1.0,
                            "produccion_anio_anterior": 100.0,
                            "produccion_promedio_5_anios": 100.0,
                            "desviacion_produccion_5_anios": 10.0,
                            "produccion_final": 100.0,
                            "rendimiento_final": 1.0,
                        }
                    )
        features = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("src.analysis.production_nowcast.make_regression_pipeline", return_value=FakeModel()),
                patch(
                    "src.analysis.production_nowcast.model_feature_importance",
                    return_value=pd.DataFrame([{"variable": "produccion_acumulada", "importancia": 1.0}]),
                ),
                patch("src.analysis.production_nowcast.joblib.dump"),
            ):
                forecast, metrics, _ = train_and_forecast_production(features, Path(temp_dir))
        self.assertEqual(metrics["modo"], "base_historica")
        self.assertFalse(metrics["xgboost_operativo"])
        self.assertIn("candidato", str(metrics["motivo"]).lower())
        self.assertTrue((forecast["produccion_pronosticada"] == 100.0).all())

    def test_forces_xgboost_for_demo_even_when_baseline_wins(self) -> None:
        class FakeModel:
            def fit(self, *_args, **_kwargs):
                return self

            def predict(self, features):
                return pd.Series([0.0] * len(features)).to_numpy()

        rows = []
        for year in (2023, 2024):
            for month in range(1, 7):
                for state in ("Michoacan", "Jalisco", "Puebla", "Nayarit", "Colima", "Morelos", "Oaxaca", "Chiapas", "Guerrero", "Veracruz"):
                    rows.append(
                        {
                            "cultivo_canonico": "aguacate",
                            "estado": state,
                            "anio": year,
                            "mes_corte": month,
                            "fecha_corte": pd.Timestamp(year=year, month=month, day=28) + pd.offsets.MonthEnd(0),
                            "superficie_sembrada_ha": 100.0,
                            "superficie_cosechada_ha": 60.0,
                            "superficie_siniestrada_ha": 5.0,
                            "produccion_acumulada": 100.0,
                            "rendimiento_actual": 1.0,
                            "produccion_anio_anterior": 100.0,
                            "produccion_promedio_5_anios": 100.0,
                            "desviacion_produccion_5_anios": 10.0,
                            "produccion_final": 100.0,
                            "rendimiento_final": 1.0,
                        }
                    )
        features = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("src.analysis.production_nowcast.make_regression_pipeline", return_value=FakeModel()),
                patch(
                    "src.analysis.production_nowcast.model_feature_importance",
                    return_value=pd.DataFrame([{"variable": "produccion_acumulada", "importancia": 1.0}]),
                ),
                patch("src.analysis.production_nowcast.joblib.dump"),
            ):
                forecast, metrics, _ = train_and_forecast_production(
                    features,
                    Path(temp_dir),
                    force_model="xgboost",
                )
        self.assertEqual(metrics["modo"], "xgboost")
        self.assertTrue(metrics["xgboost_operativo"])
        self.assertTrue(metrics["metodo_forzado"])
        self.assertEqual(metrics["metodo_forzado_nombre"], "xgboost")
        self.assertIn("demo", str(metrics["motivo"]).lower())
        self.assertTrue((forecast["produccion_pronosticada"] == 0.0).all())


if __name__ == "__main__":
    unittest.main()
