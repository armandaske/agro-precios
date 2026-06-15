import unittest
import tempfile
from pathlib import Path

import pandas as pd

from src.analysis.production_nowcast import build_crop_state_cutoff_features, train_and_forecast_production


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


if __name__ == "__main__":
    unittest.main()
