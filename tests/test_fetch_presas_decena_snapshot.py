import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.fetch_presas_decena_snapshot import (
    TargetPeriod,
    build_run_status,
    decena_from_day,
    execute_snapshot_run,
    resolve_target_period,
)


class FetchPresasDecenaSnapshotTests(unittest.TestCase):
    def test_decena_from_day_maps_expected_ranges(self) -> None:
        self.assertEqual(decena_from_day(1), 1)
        self.assertEqual(decena_from_day(10), 1)
        self.assertEqual(decena_from_day(11), 2)
        self.assertEqual(decena_from_day(20), 2)
        self.assertEqual(decena_from_day(21), 3)
        self.assertEqual(decena_from_day(31), 3)

    def test_resolve_target_period_accepts_target_date(self) -> None:
        period = resolve_target_period(target_date=date(2026, 6, 27), year=None, month=None, day_block=None)

        self.assertEqual(period, TargetPeriod(year=2026, month=6, day_block=3))

    def test_resolve_target_period_requires_complete_explicit_period(self) -> None:
        with self.assertRaisesRegex(ValueError, "debes proporcionar los tres valores"):
            resolve_target_period(target_date=None, year=2026, month=6, day_block=None)

    def test_build_run_status_marks_error_when_error_sheet_has_rows(self) -> None:
        self.assertEqual(build_run_status(row_count=0, error_count=1), "error")
        self.assertEqual(build_run_status(row_count=3, error_count=1), "partial_error")
        self.assertEqual(build_run_status(row_count=3, error_count=0), "success")

    def test_execute_snapshot_run_skips_existing_period_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            period = TargetPeriod(year=2026, month=6, day_block=3)
            run_dir = output_root / "2026" / "06"
            run_dir.mkdir(parents=True)
            existing_workbook = run_dir / "presas_decena_2026_06_d3_20260627_010000.xlsx"
            existing_workbook.write_text("placeholder", encoding="utf-8")

            summary = execute_snapshot_run(
                output_root=output_root,
                period=period,
                force=False,
                run_timestamp=datetime(2026, 6, 27, 2, 15, 0),
            )

            self.assertEqual(summary["status"], "skipped_existing")
            self.assertEqual(summary["existing_output_paths"], [str(existing_workbook.resolve())])
            summary_files = list(run_dir.glob("presas_decena_resumen_2026_06_d3_*.json"))
            self.assertEqual(len(summary_files), 1)

            payload = json.loads(summary_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "skipped_existing")

    def test_execute_snapshot_run_writes_config_output_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            period = TargetPeriod(year=2026, month=6, day_block=3)
            run_timestamp = datetime(2026, 6, 27, 2, 15, 0)

            def fake_run_from_config(config_path: Path, output_path: Path) -> Path:
                config = pd.read_excel(config_path, sheet_name="consultas")
                self.assertEqual(config.iloc[0]["tipo_consulta"], "presas_periodo")
                self.assertEqual(int(config.iloc[0]["anio"]), 2026)
                self.assertEqual(int(config.iloc[0]["mes"]), 6)
                self.assertEqual(int(config.iloc[0]["decena"]), 3)

                with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                    pd.DataFrame([{"id_conagua": "1"}]).to_excel(
                        writer,
                        sheet_name="presas_periodo",
                        index=False,
                    )
                    pd.DataFrame(columns=["error"]).to_excel(writer, sheet_name="errores", index=False)
                return output_path

            with patch("scripts.fetch_presas_decena_snapshot.run_from_config", side_effect=fake_run_from_config):
                summary = execute_snapshot_run(
                    output_root=output_root,
                    period=period,
                    force=False,
                    run_timestamp=run_timestamp,
                )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["row_count"], 1)
            self.assertEqual(summary["error_count"], 0)

            run_dir = output_root / "2026" / "06"
            workbooks = list(run_dir.glob("presas_decena_2026_06_d3_*.xlsx"))
            configs = list(run_dir.glob("presas_decena_config_2026_06_d3_*.xlsx"))
            summaries = list(run_dir.glob("presas_decena_resumen_2026_06_d3_*.json"))

            self.assertEqual(len(workbooks), 1)
            self.assertEqual(len(configs), 1)
            self.assertEqual(len(summaries), 1)

            payload = json.loads(summaries[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["row_count"], 1)
            self.assertEqual(payload["error_count"], 0)

    def test_execute_snapshot_run_marks_error_when_workbook_has_error_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            period = TargetPeriod(year=2026, month=6, day_block=3)

            def fake_run_from_config(config_path: Path, output_path: Path) -> Path:
                with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                    pd.DataFrame(columns=["id_conagua"]).to_excel(
                        writer,
                        sheet_name="presas_periodo",
                        index=False,
                    )
                    pd.DataFrame([{"error": "fallo portal"}]).to_excel(
                        writer,
                        sheet_name="errores",
                        index=False,
                    )
                return output_path

            with patch("scripts.fetch_presas_decena_snapshot.run_from_config", side_effect=fake_run_from_config):
                summary = execute_snapshot_run(
                    output_root=output_root,
                    period=period,
                    force=False,
                    run_timestamp=datetime(2026, 6, 27, 2, 15, 0),
                )

            self.assertEqual(summary["status"], "error")
            self.assertEqual(summary["row_count"], 0)
            self.assertEqual(summary["error_count"], 1)


if __name__ == "__main__":
    unittest.main()
