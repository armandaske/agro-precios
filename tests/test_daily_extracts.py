import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.run_daily_extracts import load_products_config, orchestrate_daily_run


class DailyExtractsTests(unittest.TestCase):
    def _write_products_workbook(self, path: Path, rows: list[dict]) -> None:
        df = pd.DataFrame(rows)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="productos", index=False)

    def test_load_products_config_parses_terms_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "products.xlsx"
            self._write_products_workbook(
                workbook_path,
                [
                    {
                        "activo": True,
                        "producto_canonico": "tomate",
                        "walmart_habilitado": True,
                        "terminos_busqueda_walmart": "jitomate|tomate",
                        "chedraui_habilitado": True,
                        "terminos_busqueda_chedraui": "jitomate|tomate",
                        "sniim_habilitado": True,
                        "sniim_id_producto": 133,
                        "sniim_id_origen": None,
                        "sniim_id_destino": None,
                        "sniim_id_precios_por": None,
                        "cierre_agricola_habilitado": True,
                        "cultivo_cierre_agricola": "Tomate rojo (jitomate)",
                    }
                ],
            )

            configs = load_products_config(workbook_path)

            self.assertEqual(len(configs), 1)
            config = configs[0]
            self.assertEqual(config.canonical_product, "tomate")
            self.assertEqual(config.walmart_search_terms, ["jitomate", "tomate"])
            self.assertEqual(config.sniim_origen_id, -1)
            self.assertEqual(config.sniim_destino_id, -1)
            self.assertEqual(config.sniim_precios_por_id, 2)
            self.assertEqual(config.cierre_crop_name, "Tomate rojo (jitomate)")

    def test_load_products_config_requires_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "products.xlsx"
            with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
                pd.DataFrame([{"activo": True, "producto_canonico": "aguacate"}]).to_excel(
                    writer,
                    sheet_name="productos",
                    index=False,
                )

            with self.assertRaisesRegex(ValueError, "Missing required columns"):
                load_products_config(workbook_path)

    def test_load_products_config_defaults_chedraui_when_columns_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "products.xlsx"
            self._write_products_workbook(
                workbook_path,
                [
                    {
                        "activo": True,
                        "producto_canonico": "aguacate",
                        "walmart_habilitado": True,
                        "terminos_busqueda_walmart": "aguacate",
                        "sniim_habilitado": True,
                        "sniim_id_producto": 133,
                        "sniim_id_origen": -1,
                        "sniim_id_destino": -1,
                        "sniim_id_precios_por": 2,
                        "cierre_agricola_habilitado": True,
                        "cultivo_cierre_agricola": "Aguacate",
                    }
                ],
            )

            configs = load_products_config(workbook_path)
            self.assertEqual(len(configs), 1)
            self.assertFalse(configs[0].chedraui_enabled)
            self.assertEqual(configs[0].chedraui_search_terms, ["aguacate"])

    @patch("scripts.run_daily_extracts.fetch_report_dataframe")
    @patch("scripts.run_daily_extracts.fetch_sniim_fruits_vegetables")
    @patch("scripts.run_daily_extracts.choose_best_records_chedraui")
    @patch("scripts.run_daily_extracts.collect_search_records_chedraui")
    @patch("scripts.run_daily_extracts.choose_best_records")
    @patch("scripts.run_daily_extracts.collect_search_records")
    def test_orchestrate_daily_run_writes_outputs_and_summary(
        self,
        mock_collect_search_records,
        mock_choose_best_records,
        mock_collect_search_records_chedraui,
        mock_choose_best_records_chedraui,
        mock_fetch_sniim,
        mock_fetch_cierre,
    ) -> None:
        mock_collect_search_records.return_value = [
            {
                "product_canonical": "aguacate",
                "product_raw": "Aguacate Hass por kilo",
                "source_query": "aguacate",
                "price_mxn": 49.9,
                "promo_flag": False,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 49.9,
                "fresh_produce_flag": True,
            }
        ]
        mock_choose_best_records.return_value = mock_collect_search_records.return_value
        mock_collect_search_records_chedraui.return_value = mock_collect_search_records.return_value
        mock_choose_best_records_chedraui.return_value = mock_collect_search_records.return_value
        mock_fetch_sniim.return_value = pd.DataFrame([{"precio_frecuente": 10.5, "origen": "Michoacán"}])
        mock_fetch_cierre.return_value = pd.DataFrame([{"Entidad": "Michoacán", "Producción": 100}])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "products.xlsx"
            output_root = root / "runs"
            self._write_products_workbook(
                config_path,
                [
                    {
                        "activo": True,
                        "producto_canonico": "aguacate",
                        "walmart_habilitado": True,
                        "terminos_busqueda_walmart": "aguacate|avocado",
                        "chedraui_habilitado": True,
                        "terminos_busqueda_chedraui": "aguacate|avocado",
                        "sniim_habilitado": True,
                        "sniim_id_producto": 133,
                        "sniim_id_origen": -1,
                        "sniim_id_destino": -1,
                        "sniim_id_precios_por": 2,
                        "cierre_agricola_habilitado": True,
                        "cultivo_cierre_agricola": "Aguacate",
                    },
                    {
                        "activo": True,
                        "producto_canonico": "mango",
                        "walmart_habilitado": False,
                        "terminos_busqueda_walmart": "",
                        "chedraui_habilitado": False,
                        "terminos_busqueda_chedraui": "",
                        "sniim_habilitado": True,
                        "sniim_id_producto": None,
                        "sniim_id_origen": None,
                        "sniim_id_destino": None,
                        "sniim_id_precios_por": None,
                        "cierre_agricola_habilitado": True,
                        "cultivo_cierre_agricola": "",
                    },
                ],
            )

            summary = orchestrate_daily_run(config_path, output_root, date(2026, 4, 8))
            run_dir = output_root / "2026-04-08"

            self.assertTrue((run_dir / "products_snapshot.xlsx").exists())
            self.assertTrue((run_dir / "run_summary.json").exists())
            self.assertTrue((run_dir / "walmart_2026-04-08.xlsx").exists())
            self.assertTrue((run_dir / "chedraui_2026-04-08.xlsx").exists())
            self.assertTrue((run_dir / "sniim_2026-04-08.xlsx").exists())
            self.assertTrue((run_dir / "cierre_agricola_2026-04-08.xlsx").exists())

            self.assertEqual(summary["sources"]["walmart"]["succeeded"], 1)
            self.assertEqual(summary["sources"]["chedraui"]["succeeded"], 1)
            self.assertEqual(summary["sources"]["sniim"]["failed"], 1)
            self.assertEqual(summary["sources"]["cierre_agricola"]["failed"], 1)

            self.assertEqual(
                mock_fetch_sniim.call_args.kwargs["fecha_inicio"],
                "2026-04-07",
            )
            self.assertEqual(
                mock_fetch_sniim.call_args.kwargs["fecha_final"],
                "2026-04-07",
            )
            self.assertEqual(mock_fetch_cierre.call_args.kwargs["year"], "2026")

            with pd.ExcelFile(run_dir / "sniim_2026-04-08.xlsx") as sniim_workbook:
                self.assertIn("datos", sniim_workbook.sheet_names)
                self.assertIn("errores", sniim_workbook.sheet_names)
                self.assertIn("metadatos", sniim_workbook.sheet_names)

            sniim_data = pd.read_excel(run_dir / "sniim_2026-04-08.xlsx", sheet_name="datos")
            self.assertIn("fecha_corrida", sniim_data.columns)
            self.assertIn("nombre_fuente", sniim_data.columns)
            self.assertIn("fecha_inicio_consulta", sniim_data.columns)

            walmart_data = pd.read_excel(run_dir / "walmart_2026-04-08.xlsx", sheet_name="datos")
            self.assertIn("producto_original", walmart_data.columns)
            self.assertIn("terminos_busqueda_utilizados", walmart_data.columns)


if __name__ == "__main__":
    unittest.main()
