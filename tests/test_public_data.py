import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.analysis.public_data import (
    aggregate_weather_to_decena,
    determine_nasa_fetch_window,
    merge_climate_history,
    parse_nasa_power_payload,
)


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

    def test_determine_nasa_fetch_window_uses_history_floor_without_existing_file(self) -> None:
        history = pd.DataFrame({"fecha": [pd.Timestamp("2025-01-10"), pd.Timestamp("2026-01-20")]})

        start, end, existing = determine_nasa_fetch_window(
            history,
            Path("missing.parquet"),
            end_date="2026-06-29",
        )

        self.assertEqual(start, "2025-01-10")
        self.assertEqual(end, "2026-06-29")
        self.assertTrue(existing.empty)

    def test_determine_nasa_fetch_window_applies_incremental_overlap(self) -> None:
        history = pd.DataFrame({"fecha": [pd.Timestamp("2025-01-10"), pd.Timestamp("2026-01-20")]})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "climate.parquet"
            pd.DataFrame(
                [
                    {"id_conagua": "A", "fecha": pd.Timestamp("2026-02-20")},
                    {"id_conagua": "A", "fecha": pd.Timestamp("2026-03-31")},
                ]
            ).to_parquet(output_path, index=False)

            start, end, existing = determine_nasa_fetch_window(
                history,
                output_path,
                end_date="2026-06-29",
                merge_existing=True,
                lookback_days=40,
            )

        self.assertEqual(start, "2026-02-19")
        self.assertEqual(end, "2026-06-29")
        self.assertEqual(len(existing), 2)

    def test_merge_climate_history_keeps_latest_duplicate(self) -> None:
        existing = pd.DataFrame(
            [
                {"id_conagua": "A", "fecha": pd.Timestamp("2026-01-10"), "precipitacion_mm": 1.0},
                {"id_conagua": "B", "fecha": pd.Timestamp("2026-01-10"), "precipitacion_mm": 5.0},
            ]
        )
        incoming = pd.DataFrame(
            [
                {"id_conagua": "A", "fecha": pd.Timestamp("2026-01-10"), "precipitacion_mm": 9.0},
                {"id_conagua": "A", "fecha": pd.Timestamp("2026-01-20"), "precipitacion_mm": 2.0},
            ]
        )

        merged = merge_climate_history(existing, incoming)

        self.assertEqual(len(merged), 3)
        latest_a = merged.loc[
            (merged["id_conagua"] == "A") & (merged["fecha"] == pd.Timestamp("2026-01-10"))
        ]
        self.assertEqual(float(latest_a.iloc[0]["precipitacion_mm"]), 9.0)


if __name__ == "__main__":
    unittest.main()
