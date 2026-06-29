import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.run_water_risk_refresh import atomic_publish_html, main


class RunWaterRiskRefreshTests(unittest.TestCase):
    def test_atomic_publish_html_replaces_target_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.html"
            target = temp_path / "served" / "latest.html"
            source.write_text("nuevo", encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("viejo", encoding="utf-8")

            published = atomic_publish_html(source, target)

            self.assertEqual(published, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "nuevo")
            self.assertFalse((target.parent / "latest.html.tmp").exists())

    def test_main_skips_when_decena_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            summary_path = temp_path / "summary.json"
            args = Namespace(
                publish_html_to=(temp_path / "served" / "latest.html").resolve(),
                presas_root=temp_path / "presas",
                decena_output_root=temp_path / "presas" / "decena",
                water_output_dir=temp_path / "analysis",
                climate_output=temp_path / "climate.parquet",
                summary_path=summary_path,
                target_date=None,
                year=2026,
                month=6,
                decena=3,
                force_decena_fetch=False,
                lookback_days=40,
                climate_state=None,
                climate_limit=None,
                climate_pause_seconds=0.2,
            )

            with (
                patch("scripts.run_water_risk_refresh.parse_args", return_value=args),
                patch(
                    "scripts.run_water_risk_refresh.execute_snapshot_run",
                    return_value={"status": "skipped_existing", "output_path": None},
                ),
                patch("scripts.run_water_risk_refresh.fetch_nasa_power_weather") as climate_mock,
                patch("scripts.run_water_risk_refresh.run_water_risk_pipeline") as model_mock,
                patch("scripts.run_water_risk_refresh.atomic_publish_html") as publish_mock,
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            climate_mock.assert_not_called()
            model_mock.assert_not_called()
            publish_mock.assert_not_called()
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "skipped_existing")
            self.assertEqual(summary["decena_status"], "skipped_existing")
            self.assertEqual(summary["model_status"], "not_run")

    def test_main_uses_existing_climate_fallback_when_refresh_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            summary_path = temp_path / "summary.json"
            climate_output = temp_path / "climate.parquet"
            pd.DataFrame(
                [{"id_conagua": "A", "fecha": pd.Timestamp("2026-05-31"), "precipitacion_mm": 1.0}]
            ).to_parquet(climate_output, index=False)
            publish_target = (temp_path / "served" / "latest.html").resolve()
            args = Namespace(
                publish_html_to=publish_target,
                presas_root=temp_path / "presas",
                decena_output_root=temp_path / "presas" / "decena",
                water_output_dir=temp_path / "analysis",
                climate_output=climate_output,
                summary_path=summary_path,
                target_date=None,
                year=2026,
                month=6,
                decena=3,
                force_decena_fetch=False,
                lookback_days=40,
                climate_state=None,
                climate_limit=None,
                climate_pause_seconds=0.2,
            )

            def fake_model_run(_presas_root: Path, output_dir: Path, *, climate_path: Path, **_kwargs):
                self.assertEqual(climate_path, climate_output)
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "monitoreo_riesgo_hidrico.html").write_text("html", encoding="utf-8")
                return {"alertas": 1}

            with (
                patch("scripts.run_water_risk_refresh.parse_args", return_value=args),
                patch(
                    "scripts.run_water_risk_refresh.execute_snapshot_run",
                    return_value={"status": "success", "output_path": str(temp_path / "snapshot.xlsx")},
                ),
                patch(
                    "scripts.run_water_risk_refresh.fetch_nasa_power_weather",
                    side_effect=RuntimeError("nasa down"),
                ),
                patch(
                    "scripts.run_water_risk_refresh.run_water_risk_pipeline",
                    side_effect=fake_model_run,
                ),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "updated")
            self.assertEqual(summary["climate_status"], "stale_fallback")
            self.assertTrue(summary["used_existing_climate_fallback"])
            self.assertEqual(publish_target.read_text(encoding="utf-8"), "html")

    def test_main_fails_on_partial_decena_error_without_publishing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            publish_target = (temp_path / "served" / "latest.html").resolve()
            publish_target.parent.mkdir(parents=True, exist_ok=True)
            publish_target.write_text("anterior", encoding="utf-8")
            summary_path = temp_path / "summary.json"
            args = Namespace(
                publish_html_to=publish_target,
                presas_root=temp_path / "presas",
                decena_output_root=temp_path / "presas" / "decena",
                water_output_dir=temp_path / "analysis",
                climate_output=temp_path / "climate.parquet",
                summary_path=summary_path,
                target_date=None,
                year=2026,
                month=6,
                decena=3,
                force_decena_fetch=False,
                lookback_days=40,
                climate_state=None,
                climate_limit=None,
                climate_pause_seconds=0.2,
            )

            with (
                patch("scripts.run_water_risk_refresh.parse_args", return_value=args),
                patch(
                    "scripts.run_water_risk_refresh.execute_snapshot_run",
                    return_value={"status": "partial_error", "output_path": None},
                ),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 1)
            self.assertEqual(publish_target.read_text(encoding="utf-8"), "anterior")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "error")
            self.assertEqual(summary["decena_status"], "partial_error")


if __name__ == "__main__":
    unittest.main()
