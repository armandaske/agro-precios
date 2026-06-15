import unittest

import pandas as pd

from src.analysis.water_risk import (
    _risk_level,
    build_dam_decena_features,
    build_state_decena_features,
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


if __name__ == "__main__":
    unittest.main()
