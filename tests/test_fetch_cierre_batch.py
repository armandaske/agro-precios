import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.fetch_cierre_batch import fetch_cierre_batch, load_batch_items
from src.extract.spreadsheet_localization import ARCHIVO_RESUMEN_LOTE_CIERRE


class FetchCierreBatchTests(unittest.TestCase):
    def _write_products_workbook(self, path: Path, rows: list[dict]) -> None:
        df = pd.DataFrame(rows)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="productos", index=False)

    def test_load_batch_items_uses_fallback_crop_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "products.xlsx"
            self._write_products_workbook(
                config_path,
                [
                    {
                        "activo": True,
                        "producto_canonico": "tomate rojo",
                        "cultivo_cierre_agricola": "",
                    }
                ],
            )

            items = load_batch_items(config_path)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].canonical_product, "tomate rojo")
            self.assertEqual(items[0].cierre_crop_name, "Tomate rojo (jitomate)")

    @patch("scripts.fetch_cierre_batch.build_report")
    def test_fetch_cierre_batch_writes_spanish_summary_name(self, mock_build_report) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "products.xlsx"
            output_root = root / "salidas"
            self._write_products_workbook(
                config_path,
                [
                    {
                        "activo": True,
                        "producto_canonico": "aguacate",
                        "cultivo_cierre_agricola": "Aguacate",
                    }
                ],
            )

            summary = fetch_cierre_batch(
                config_path=config_path,
                output_root=output_root,
                years=[2024],
                output_format="xlsx",
            )

            self.assertTrue((output_root / ARCHIVO_RESUMEN_LOTE_CIERRE).exists())
            self.assertFalse((output_root / "batch_summary.json").exists())
            self.assertEqual(summary["requested_products"], 1)
            self.assertEqual(summary["requested_jobs"], 1)
            self.assertEqual(summary["succeeded_jobs"], 1)
            self.assertIn(ARCHIVO_RESUMEN_LOTE_CIERRE, summary["summary_path"])
            self.assertEqual(mock_build_report.call_args.kwargs["crop"], "Aguacate")
            self.assertEqual(mock_build_report.call_args.kwargs["year"], "2024")


if __name__ == "__main__":
    unittest.main()
