import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.fetch_cierre_batch import fetch_cierre_batch


class FetchCierreBatchTests(unittest.TestCase):
    @patch("scripts.fetch_cierre_batch.build_report")
    def test_fetch_cierre_batch_writes_into_run_subfolder(self, mock_build_report) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "products.xlsx"
            output_root = root / "out"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "producto_canonico": "Aguacate",
                        "cultivo_cierre_agricola": "Aguacate",
                    }
                ]
            )
            with pd.ExcelWriter(config, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="productos", index=False)

            summary = fetch_cierre_batch(
                config_path=config,
                output_root=output_root,
                years=[2024],
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
