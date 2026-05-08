import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_master_price_workbook import (
    _read_source_workbook,
    build_cierre_annual_stats,
    build_master_workbook,
    build_sniim_daily_stats,
    build_retail_daily_panel,
)


class BuildMasterPriceWorkbookTests(unittest.TestCase):
    def _write_workbook(
        self,
        path: Path,
        data_df: pd.DataFrame,
        meta_df: pd.DataFrame | None = None,
        *,
        localized: bool,
    ) -> None:
        data_sheet = "datos" if localized else "data"
        meta_sheet = "metadatos" if localized else "meta"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            data_df.to_excel(writer, sheet_name=data_sheet, index=False)
            (meta_df if meta_df is not None else pd.DataFrame([{}])).to_excel(
                writer,
                sheet_name=meta_sheet,
                index=False,
            )

    def _write_products_snapshot(self, path: Path) -> None:
        df = pd.DataFrame(
            [
                {
                    "activo": True,
                    "producto_canonico": "aguacate",
                    "walmart_habilitado": True,
                    "terminos_busqueda_walmart": "aguacate",
                    "chedraui_habilitado": True,
                    "terminos_busqueda_chedraui": "aguacate",
                    "sniim_habilitado": True,
                    "sniim_id_producto": 133,
                    "sniim_id_origen": -1,
                    "sniim_id_destino": -1,
                    "sniim_id_precios_por": 2,
                    "cierre_agricola_habilitado": True,
                    "cultivo_cierre_agricola": "Aguacate",
                }
            ]
        )
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="productos", index=False)

    def test_read_source_workbook_supports_legacy_and_localized_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "walmart_legacy.xlsx"
            localized = root / "walmart_localized.xlsx"

            self._write_workbook(
                legacy,
                pd.DataFrame(
                    [
                        {
                            "price_mxn": 49.9,
                            "estimated_price_per_kg_mxn": 49.9,
                            "run_date": "2026-04-18",
                            "canonical_product": "aguacate",
                        }
                    ]
                ),
                localized=False,
            )
            self._write_workbook(
                localized,
                pd.DataFrame(
                    [
                        {
                            "precio_mxn": 49.9,
                            "precio_estimado_por_kg_mxn": 49.9,
                            "fecha_corrida": "2026-04-18",
                            "producto_canonico.1": "aguacate",
                        }
                    ]
                ),
                localized=True,
            )

            legacy_df, _, _ = _read_source_workbook(legacy, "walmart")
            localized_df, _, _ = _read_source_workbook(localized, "walmart")

            self.assertIn("price_mxn", legacy_df.columns)
            self.assertIn("estimated_price_per_kg_mxn", localized_df.columns)
            self.assertEqual(str(localized_df.iloc[0]["canonical_product"]), "aguacate")

    def test_build_sniim_daily_stats_aggregates_mean_median_and_count(self) -> None:
        df = pd.DataFrame(
            [
                {"run_date": "2026-04-18", "canonical_product": "aguacate", "precio_frecuente": 10.0},
                {"run_date": "2026-04-18", "canonical_product": "aguacate", "precio_frecuente": 20.0},
                {"run_date": "2026-04-18", "canonical_product": "aguacate", "precio_frecuente": 30.0},
            ]
        )

        stats = build_sniim_daily_stats(df)

        self.assertEqual(float(stats.iloc[0]["sniim_daily_mean_mxn"]), 20.0)
        self.assertEqual(float(stats.iloc[0]["sniim_daily_median_mxn"]), 20.0)
        self.assertEqual(float(stats.iloc[0]["sniim_daily_min_mxn"]), 10.0)
        self.assertEqual(float(stats.iloc[0]["sniim_daily_max_mxn"]), 30.0)
        self.assertEqual(int(stats.iloc[0]["sniim_source_row_count"]), 3)

    def test_build_retail_daily_panel_prefers_per_kg_price_and_falls_back_to_raw(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "run_date": "2026-04-18",
                    "canonical_product": "aguacate",
                    "price_mxn": 50.0,
                    "estimated_price_per_kg_mxn": 49.0,
                    "unit_raw": "kg",
                },
                {
                    "run_date": "2026-04-18",
                    "canonical_product": "elote",
                    "price_mxn": 15.0,
                    "estimated_price_per_kg_mxn": pd.NA,
                    "unit_raw": "pieza",
                },
            ]
        )

        panel = build_retail_daily_panel(df, "walmart")

        self.assertEqual(float(panel.iloc[0]["comparison_price_mxn"]), 49.0)
        self.assertEqual(str(panel.iloc[0]["price_basis"]), "estimated_price_per_kg_mxn")
        self.assertEqual(float(panel.iloc[1]["comparison_price_mxn"]), 15.0)
        self.assertEqual(str(panel.iloc[1]["price_basis"]), "price_mxn_fallback")

    def test_build_cierre_annual_stats_uses_weighted_pmr(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "query_year": 2024,
                    "canonical_product": "aguacate",
                    "cierre_unit_label": "ton",
                    "pmr_mxn_udm": 10.0,
                    "produccion": 100.0,
                    "cierre_crop_name": "Aguacate",
                    "cierre_crop_label_raw": "Aguacate (ton)",
                },
                {
                    "query_year": 2024,
                    "canonical_product": "aguacate",
                    "cierre_unit_label": "ton",
                    "pmr_mxn_udm": 20.0,
                    "produccion": 300.0,
                    "cierre_crop_name": "Aguacate",
                    "cierre_crop_label_raw": "Aguacate (ton)",
                },
            ]
        )

        stats = build_cierre_annual_stats(df)

        self.assertAlmostEqual(float(stats.iloc[0]["cierre_annual_weighted_pmr_mxn_udm"]), 17.5)
        self.assertEqual(int(stats.iloc[0]["cierre_rows_used"]), 2)
        self.assertEqual(float(stats.iloc[0]["cierre_total_produccion"]), 400.0)

    def test_build_master_workbook_writes_expected_sheets_and_repeats_cierre(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            daily_root = root / "daily_runs"
            cierre_root = root / "cierre_exports"
            output_path = root / "analysis" / "master.xlsx"
            cierre_root.mkdir(parents=True, exist_ok=True)

            run_18 = daily_root / "2026-04-18"
            run_19 = daily_root / "2026-04-19"
            run_18.mkdir(parents=True, exist_ok=True)
            run_19.mkdir(parents=True, exist_ok=True)
            self._write_products_snapshot(run_18 / "products_snapshot.xlsx")
            self._write_products_snapshot(run_19 / "products_snapshot.xlsx")

            self._write_workbook(
                run_18 / "sniim_2026-04-18.xlsx",
                pd.DataFrame(
                    [
                        {
                            "presentacion": "Kilogramo",
                            "origen": "Michoacán",
                            "destino": "Aguascalientes",
                            "precio_frecuente": 40.0,
                            "fecha_corrida": "2026-04-18",
                            "producto_canonico": "aguacate",
                        },
                        {
                            "presentacion": "Kilogramo",
                            "origen": "Michoacán",
                            "destino": "León",
                            "precio_frecuente": 50.0,
                            "fecha_corrida": "2026-04-18",
                            "producto_canonico": "aguacate",
                        },
                    ]
                ),
                localized=True,
            )
            self._write_workbook(
                run_19 / "sniim_2026-04-19.xlsx",
                pd.DataFrame(
                    [
                        {
                            "presentacion": "Kilogramo",
                            "origen": "Michoacán",
                            "destino": "Aguascalientes",
                            "precio_frecuente": 60.0,
                            "fecha_corrida": "2026-04-19",
                            "producto_canonico": "aguacate",
                        }
                    ]
                ),
                localized=True,
            )

            self._write_workbook(
                run_18 / "walmart_2026-04-18.xlsx",
                pd.DataFrame(
                    [
                        {
                            "precio_mxn": 54.0,
                            "precio_estimado_por_kg_mxn": 52.0,
                            "unidad_detectada": "kg",
                            "producto_original": "Aguacate Hass por kilo",
                            "producto_inferido": "aguacate",
                            "pagina_fuente": "https://walmart.example/aguacate",
                            "terminos_busqueda_utilizados": "aguacate",
                            "fecha_corrida": "2026-04-18",
                            "producto_canonico.1": "aguacate",
                        }
                    ]
                ),
                localized=True,
            )
            self._write_workbook(
                run_19 / "walmart_2026-04-19.xlsx",
                pd.DataFrame(
                    [
                        {
                            "precio_mxn": 56.0,
                            "precio_estimado_por_kg_mxn": pd.NA,
                            "unidad_detectada": "kg",
                            "producto_original": "Aguacate Hass por kilo",
                            "producto_inferido": "aguacate",
                            "pagina_fuente": "https://walmart.example/aguacate",
                            "terminos_busqueda_utilizados": "aguacate",
                            "fecha_corrida": "2026-04-19",
                            "producto_canonico.1": "aguacate",
                        }
                    ]
                ),
                localized=True,
            )

            self._write_workbook(
                run_18 / "chedraui_2026-04-18.xlsx",
                pd.DataFrame(
                    [
                        {
                            "precio_mxn": 55.0,
                            "precio_estimado_por_kg_mxn": 53.0,
                            "unidad_detectada": "kg",
                            "producto_original": "Aguacate Hass por Kg",
                            "producto_inferido": "aguacate",
                            "pagina_fuente": "https://chedraui.example/aguacate",
                            "terminos_busqueda_utilizados": "aguacate",
                            "fecha_corrida": "2026-04-18",
                            "producto_canonico.1": "aguacate",
                        }
                    ]
                ),
                localized=True,
            )
            self._write_workbook(
                run_19 / "chedraui_2026-04-19.xlsx",
                pd.DataFrame(
                    [
                        {
                            "precio_mxn": 57.0,
                            "precio_estimado_por_kg_mxn": 54.0,
                            "unidad_detectada": "kg",
                            "producto_original": "Aguacate Hass por Kg",
                            "producto_inferido": "aguacate",
                            "pagina_fuente": "https://chedraui.example/aguacate",
                            "terminos_busqueda_utilizados": "aguacate",
                            "fecha_corrida": "2026-04-19",
                            "producto_canonico.1": "aguacate",
                        }
                    ]
                ),
                localized=True,
            )

            self._write_workbook(
                cierre_root / "aguacate_2026.xlsx",
                pd.DataFrame(
                    [
                        {
                            "entidad": "Michoacán",
                            "produccion": 100.0,
                            "pmr_mxn_udm": 10.0,
                            "cierre_crop_label_raw": "Aguacate (ton)",
                            "cierre_unit_label": "ton",
                            "cierre_crop_name": "Aguacate",
                            "query_year": 2026,
                        },
                        {
                            "entidad": "Jalisco",
                            "produccion": 300.0,
                            "pmr_mxn_udm": 14.0,
                            "cierre_crop_label_raw": "Aguacate (ton)",
                            "cierre_unit_label": "ton",
                            "cierre_crop_name": "Aguacate",
                            "query_year": 2026,
                        },
                    ]
                ),
                localized=False,
            )

            tables = build_master_workbook(daily_root, cierre_root, output_path)

            self.assertTrue(output_path.exists())
            self.assertEqual(
                set(tables.keys()),
                {
                    "panel_daily_long",
                    "compare_daily_wide",
                    "sniim_daily_stats",
                    "cierre_annual_stats",
                    "coverage",
                },
            )

            compare = tables["compare_daily_wide"]
            self.assertEqual(len(compare), 2)
            self.assertIn("walmart_comparison_mxn", compare.columns)
            self.assertIn("chedraui_comparison_mxn", compare.columns)
            self.assertIn("cierre_annual_weighted_pmr_mxn_udm", compare.columns)
            self.assertAlmostEqual(float(compare.iloc[0]["sniim_daily_mean_mxn"]), 45.0)
            self.assertAlmostEqual(float(compare.iloc[0]["cierre_annual_weighted_pmr_mxn_udm"]), 13.0)
            self.assertTrue(compare["cierre_unit_label"].eq("ton").all())

            with pd.ExcelFile(output_path) as workbook:
                self.assertEqual(
                    set(workbook.sheet_names),
                    {
                        "panel_daily_long",
                        "compare_daily_wide",
                        "sniim_daily_stats",
                        "cierre_annual_stats",
                        "coverage",
                    },
                )


if __name__ == "__main__":
    unittest.main()
