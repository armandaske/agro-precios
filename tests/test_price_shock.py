import unittest
import tempfile
from pathlib import Path

import pandas as pd

from src.analysis.price_shock import (
    build_margin_anomalies,
    build_price_product_market_features,
)


class PriceShockFeatureTests(unittest.TestCase):
    def test_builds_daily_lags_targets_and_margin_anomalies(self) -> None:
        dates = pd.date_range("2026-01-01", periods=40, freq="D")
        wholesale = pd.DataFrame(
            [
                {
                    "fecha": current_date,
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 40 + index,
                    "precio_minimo": 38 + index,
                    "precio_maximo": 42 + index,
                }
                for index, current_date in enumerate(dates)
            ]
        )
        spreads = pd.DataFrame(
            {
                "fecha": dates,
                "cultivo_canonico": ["aguacate"] * len(dates),
                "precio_mayoreo": [40 + index for index in range(len(dates))],
                "precio_walmart": [60 + index for index in range(len(dates))],
                "spread_walmart": [0.5] * 39 + [3.0],
                "precio_chedraui": [58 + index for index in range(len(dates))],
                "spread_chedraui": [0.45] * len(dates),
            }
        )
        features = build_price_product_market_features(
            wholesale,
            spreads,
            horizons=(7,),
        )
        self.assertEqual(float(features.iloc[7]["precio_lag_7"]), 40)
        self.assertEqual(float(features.iloc[0]["objetivo_precio_h7"]), 47)

        anomalies = build_margin_anomalies(spreads)
        self.assertFalse(anomalies.empty)
        self.assertIn("puntaje_anomalia", anomalies.columns)

    def test_international_features_merge_only_model_features(self) -> None:
        dates = pd.date_range("2026-01-01", periods=15, freq="D")
        wholesale = pd.DataFrame(
            [
                {
                    "fecha": current_date,
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 40 + index,
                    "precio_minimo": 38 + index,
                    "precio_maximo": 42 + index,
                }
                for index, current_date in enumerate(dates)
            ]
        )
        spreads = pd.DataFrame(
            {
                "fecha": dates,
                "cultivo_canonico": ["aguacate"] * len(dates),
                "precio_mayoreo": [40 + index for index in range(len(dates))],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "international.parquet"
            pd.DataFrame(
                [
                    {
                        "fecha": "2026-01-01",
                        "fecha_disponible": "2026-01-01",
                        "producto_canonico": "aguacate",
                        "proxy_id": "fx_usdmxn",
                        "valor_modelo": 17.0,
                        "cambio_1_periodo": 0.01,
                        "cambio_3_periodos": 0.03,
                        "zscore_12_periodos": 0.5,
                        "uso_modelo": "feature",
                    },
                    {
                        "fecha": "2026-01-01",
                        "fecha_disponible": "2026-01-01",
                        "producto_canonico": "aguacate",
                        "proxy_id": "world_bank_orange",
                        "valor_modelo": 2.0,
                        "cambio_1_periodo": 0.02,
                        "cambio_3_periodos": 0.04,
                        "zscore_12_periodos": 0.7,
                        "uso_modelo": "diagnostico_only",
                    },
                ]
            ).to_parquet(path, index=False)

            features = build_price_product_market_features(
                wholesale,
                spreads,
                international_features_path=path,
                horizons=(7,),
            )

        self.assertIn("intl_fx_usdmxn_valor_modelo", features.columns)
        self.assertNotIn("intl_world_bank_orange_valor_modelo", features.columns)


if __name__ == "__main__":
    unittest.main()
