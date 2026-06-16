import unittest
import tempfile
from pathlib import Path

import pandas as pd

from src.analysis.water_risk import (
    _risk_level,
    build_dam_decena_features,
    build_state_decena_features,
    train_water_models,
    write_water_dashboard,
)


class WaterRiskFeatureTests(unittest.TestCase):
    def test_risk_level_respects_nested_thresholds(self) -> None:
        self.assertEqual(_risk_level(35, 0.9, 0.1, 0.0), "medio")
        self.assertEqual(_risk_level(22, 1.0, 0.8, 0.1), "alto")
        self.assertEqual(_risk_level(12, 1.0, 1.0, 0.8), "critico")

    def test_builds_lags_targets_and_state_aggregation(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "id_conagua": "A",
                    "nombre_presa": "Presa A",
                    "estado": "Jalisco",
                    "municipio": "X",
                    "uso_principal": "Riego",
                    "distrito_riego": "DR1",
                    "anio": 2025,
                    "mes": month,
                    "decena": block,
                    "fecha": pd.Timestamp(2025, month, 10 if block == 1 else 20),
                    "porcentaje_almacenamiento": 80 - index,
                    "almacenamiento_hm3": 80 - index,
                    "capacidad_name_hm3": 100,
                    "capacidad_namo_hm3": 100,
                    "latitud": 20,
                    "longitud": -103,
                    "fuente": "test",
                    "fecha_extraccion": "2025-06-01",
                    "archivo_fuente": "fixture.xlsx",
                }
                for index, (month, block) in enumerate(
                    [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2), (4, 1)]
                )
            ]
        )
        features = build_dam_decena_features(history, horizons=(1, 3))

        self.assertEqual(float(features.iloc[1]["porcentaje_lag_1"]), 80)
        self.assertEqual(float(features.iloc[0]["objetivo_porcentaje_h1"]), 79)
        self.assertEqual(float(features.iloc[0]["objetivo_porcentaje_h3"]), 77)

        state = build_state_decena_features(features)
        self.assertEqual(int(state.iloc[0]["presas_observadas"]), 1)
        self.assertEqual(float(state.iloc[0]["porcentaje_ponderado_capacidad"]), 80)

    def test_water_dashboard_shows_all_horizons(self) -> None:
        alerts = pd.DataFrame(
            [
                {
                    "id_conagua": "A",
                    "nombre_presa": "Presa A",
                    "estado": "Jalisco",
                    "municipio": "X",
                    "fecha": pd.Timestamp("2026-05-31"),
                    "porcentaje_almacenamiento": 40.0,
                    "porcentaje_pronosticado": 35.0,
                    "probabilidad_bajo_40": 0.7,
                    "probabilidad_bajo_25": 0.1,
                    "probabilidad_bajo_15": 0.0,
                    "nivel_riesgo": "medio",
                    "latitud": 20.0,
                    "longitud": -103.0,
                    "horizonte_dias": 10,
                },
                {
                    "id_conagua": "A",
                    "nombre_presa": "Presa A",
                    "estado": "Jalisco",
                    "municipio": "X",
                    "fecha": pd.Timestamp("2026-05-31"),
                    "porcentaje_almacenamiento": 40.0,
                    "porcentaje_pronosticado": 30.0,
                    "probabilidad_bajo_40": 0.9,
                    "probabilidad_bajo_25": 0.3,
                    "probabilidad_bajo_15": 0.0,
                    "nivel_riesgo": "medio",
                    "latitud": 20.0,
                    "longitud": -103.0,
                    "horizonte_dias": 30,
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "dashboard.html"
            write_water_dashboard(alerts, output)
            html = output.read_text(encoding="utf-8")

        self.assertIn("10 dias", html)
        self.assertIn("30 dias", html)
        self.assertIn("Horizonte a 10 dias", html)
        self.assertIn("Horizonte a 30 dias", html)

    def test_train_water_models_can_force_xgboost(self) -> None:
        rows = []
        for dam_index, dam_id in enumerate(["A", "B", "C", "D"], start=1):
            for step in range(60):
                rows.append(
                    {
                        "id_conagua": dam_id,
                        "nombre_presa": f"Presa {dam_id}",
                        "estado": "Jalisco",
                        "municipio": "X",
                        "uso_principal": "Riego",
                        "distrito_riego": "DR1",
                        "anio": 2025 + (step // 36),
                        "mes": (step % 12) + 1,
                        "decena": (step % 3) + 1,
                        "fecha": pd.Timestamp("2024-01-01") + pd.Timedelta(days=10 * step),
                        "porcentaje_almacenamiento": max(5.0, 80.0 - step - dam_index),
                        "almacenamiento_hm3": max(5.0, 80.0 - step - dam_index),
                        "capacidad_name_hm3": 100.0,
                        "capacidad_namo_hm3": 100.0,
                        "latitud": 20.0,
                        "longitud": -103.0,
                        "fuente": "test",
                        "fecha_extraccion": "2025-06-01",
                        "archivo_fuente": "fixture.xlsx",
                    }
                )
        history = pd.DataFrame(rows)
        features = build_dam_decena_features(history, horizons=(1,))

        with tempfile.TemporaryDirectory() as temp_dir:
            alerts, metrics, _importance = train_water_models(
                features,
                Path(temp_dir),
                horizons=(1,),
                force_model="xgboost",
            )

        self.assertTrue(bool(metrics["horizonte_1_decenas"]["metodo_forzado"]))
        self.assertEqual(metrics["horizonte_1_decenas"]["metodo_forzado_nombre"], "xgboost")
        self.assertTrue(alerts["metodo_forzado"].all())
        self.assertTrue((alerts["metodo_pronostico"] == "xgboost").all())


if __name__ == "__main__":
    unittest.main()
