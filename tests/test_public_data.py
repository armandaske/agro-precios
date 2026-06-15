import unittest

import pandas as pd

from src.analysis.public_data import aggregate_weather_to_decena, parse_nasa_power_payload


class PublicDataTests(unittest.TestCase):
    def test_parses_and_aggregates_nasa_power_payload(self) -> None:
        payload = {
            "properties": {
                "parameter": {
                    "PRECTOTCORR": {"20260101": 2.0, "20260102": 3.0},
                    "T2M": {"20260101": 20.0, "20260102": 22.0},
                    "T2M_MAX": {"20260101": 30.0, "20260102": 32.0},
                    "T2M_MIN": {"20260101": 10.0, "20260102": 12.0},
                    "EVPTRNS": {"20260101": 1.0, "20260102": 1.5},
                }
            }
        }
        daily = parse_nasa_power_payload(
            payload,
            id_conagua="A",
            latitude=20,
            longitude=-103,
        )
        decena = aggregate_weather_to_decena(daily)
        self.assertEqual(float(decena.iloc[0]["precipitacion_mm"]), 5)
        self.assertEqual(float(decena.iloc[0]["temperatura_c"]), 21)
        self.assertEqual(pd.Timestamp(decena.iloc[0]["fecha"]), pd.Timestamp("2026-01-10"))


if __name__ == "__main__":
    unittest.main()
