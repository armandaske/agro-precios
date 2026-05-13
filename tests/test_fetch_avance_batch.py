import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.fetch_avance_batch import load_batch_items


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


if __name__ == "__main__":
    unittest.main()
