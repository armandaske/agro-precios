import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.fetch_avance_batch import fetch_avance_batch, load_batch_items


class FetchAvanceBatchTests(unittest.TestCase):
    def test_load_batch_items_uses_only_active_enabled_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "products.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "producto_canonico": "Aguacate",
                        "avance_agricola_habilitado": True,
                        "cultivo_avance_agricola": "Aguacate",
                    },
                    {
                        "activo": True,
                        "producto_canonico": "Mango",
                        "avance_agricola_habilitado": False,
                        "cultivo_avance_agricola": "Mango",
                    },
                    {
                        "activo": False,
                        "producto_canonico": "Papa",
                        "avance_agricola_habilitado": True,
                        "cultivo_avance_agricola": "Papa",
                    },
                ]
            )
            with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="productos", index=False)

            items = load_batch_items(workbook_path)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].canonical_product, "Aguacate")
            self.assertEqual(items[0].avance_crop_name, "Aguacate")

    @patch("scripts.fetch_avance_batch.build_report")
    def test_fetch_avance_batch_writes_into_run_subfolder(self, mock_build_report) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "products.xlsx"
            output_root = root / "out"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "producto_canonico": "Aguacate",
                        "avance_agricola_habilitado": True,
                        "cultivo_avance_agricola": "Aguacate",
                    }
                ]
            )
            with pd.ExcelWriter(config, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="productos", index=False)

            summary = fetch_avance_batch(
                config_path=config,
                output_root=output_root,
                year=2026,
                month="Febrero",
                output_format="xlsx",
            )

            run_dir = Path(summary["run_dir"])
            self.assertTrue(run_dir.parent == output_root)
            self.assertTrue(run_dir.exists())
            self.assertTrue(Path(summary["summary_path"]).parent == run_dir)
            self.assertTrue(Path(summary["jobs"][0]["output_path"]).parent == run_dir)
            self.assertIn("run_", run_dir.name)
            mock_build_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
