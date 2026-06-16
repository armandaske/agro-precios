import unittest
import tempfile
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
