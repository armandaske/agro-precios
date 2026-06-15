import unittest

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


if __name__ == "__main__":
    unittest.main()
