import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.extract.presas_agricolas import (
    CATALOG_SHEET_NAME,
    QUERY_SHEET_NAME,
    _filter_snapshot_by_state,
    _iter_catalog_periods,
    _iter_forward_periods,
    _normalize_portal_record,
    _resolve_id_from_catalog,
    build_catalog_dataframe,
    build_default_config_dataframe,
    load_queries_config,
)


class PresasAgricolasTests(unittest.TestCase):
    def test_normalize_portal_record_decodes_entities_and_casts_numbers(self) -> None:
        record = {
            "CveCONAGUAPresa": "3524",
            "X": "-99.5547",
            "Y": "24.236",
            "nombreOficial": "Pedro Jos&eacute; M&eacute;ndez",
            "nombreComun": "Pedro Jos&eacute; M&eacute;ndez",
            "nombreEstado": "Tamaulipas",
            "nombreMpio": "San Jos&eacute; de Gracia",
            "nombreUso": "Riego y abrevadero",
            "DRiego": "R&iacute;o Soto La Marina                                ",
            "anio": "2026",
            "cveMes": "4",
            "cveDecena": "3",
            "porcAlmacen": "100.8",
            "Almacenamiento": "31.50",
            "NAME": "38.36",
            "NAMO": "31.26",
            "LinkPresa": "https://presas.conagua.gob.mx/inventario/tgeneralidades.aspx?DSP,3524",
        }

        normalized = _normalize_portal_record(record)

        self.assertEqual(normalized["nombre_oficial"], "Pedro José Méndez")
        self.assertEqual(normalized["municipio"], "San José de Gracia")
        self.assertEqual(normalized["distrito_riego"], "Río Soto La Marina")
        self.assertEqual(normalized["anio"], 2026)
        self.assertEqual(normalized["mes"], 4)
        self.assertEqual(normalized["decena"], 3)
        self.assertAlmostEqual(float(normalized["porcentaje_almacenamiento"]), 100.8)
        self.assertAlmostEqual(float(normalized["latitud"]), 24.236)
        self.assertAlmostEqual(float(normalized["longitud"]), -99.5547)

    def test_build_default_config_dataframe_prefills_snapshot_state_and_series(self) -> None:
        df = build_default_config_dataframe(default_year=2026, default_month=4, default_day_block=3)

        self.assertEqual(df["query_type"].tolist(), ["presas_periodo", "presas_estado", "serie_presa"])
        self.assertEqual(df.iloc[0]["year"], 2026)
        self.assertEqual(df.iloc[1]["state"], "Tamaulipas")
        self.assertEqual(df.iloc[2]["id_conagua"], "3524")
        self.assertEqual(df.iloc[2]["start_year"], 2017)

    def test_load_queries_config_applies_default_series_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "presas.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "nombre_consulta": "historico",
                        "tipo_consulta": "serie_presa",
                        "id_conagua": "3524",
                        "anio": 2026,
                        "mes": 4,
                        "decena": 3,
                        "anio_inicial": "",
                        "anio_final": 2026,
                    }
                ]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)

            queries = load_queries_config(path)

            self.assertEqual(len(queries), 1)
            self.assertEqual(queries[0].start_year, 2017)
            self.assertEqual(queries[0].end_year, 2026)

    def test_load_queries_config_supports_name_based_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "presas.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "nombre_consulta": "historico",
                        "tipo_consulta": "serie_presa",
                        "id_conagua": "",
                        "nombre_oficial": "Pedro José Méndez",
                        "estado": "Tamaulipas",
                        "anio": 2026,
                        "mes": 4,
                        "decena": 3,
                        "anio_inicial": "",
                        "anio_final": 2026,
                    }
                ]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)

            queries = load_queries_config(path)

            self.assertIsNone(queries[0].id_conagua)
            self.assertEqual(queries[0].dam_name, "Pedro José Méndez")
            self.assertEqual(queries[0].state, "Tamaulipas")

    def test_load_queries_config_requires_state_for_presas_estado(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "presas.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "nombre_consulta": "lote_estado",
                        "tipo_consulta": "presas_estado",
                        "anio": 2026,
                        "mes": 4,
                        "decena": 3,
                        "estado": "",
                    }
                ]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)

            with self.assertRaisesRegex(ValueError, "estado es obligatorio para presas_estado"):
                load_queries_config(path)

    def test_resolve_id_from_catalog_matches_name_and_state(self) -> None:
        catalog_df = pd.DataFrame(
            [
                {
                    "id_conagua": "3524",
                    "nombre_oficial": "Pedro José Méndez",
                    "nombre_comun": "Pedro José Méndez",
                    "estado": "Tamaulipas",
                },
                {
                    "id_conagua": "9999",
                    "nombre_oficial": "Pedro José Méndez",
                    "nombre_comun": "Pedro José Méndez",
                    "estado": "Nuevo León",
                },
            ]
        )
        query = load_queries_config_from_rows(
            [
                {
                    "activo": True,
                    "nombre_consulta": "historico",
                    "tipo_consulta": "serie_presa",
                    "id_conagua": "",
                    "nombre_oficial": "Pedro José Méndez",
                    "estado": "Tamaulipas",
                    "anio": 2026,
                    "mes": 4,
                    "decena": 3,
                    "anio_inicial": 2017,
                    "anio_final": 2026,
                }
            ]
        )[0]

        resolved = _resolve_id_from_catalog(query, catalog_df)

        self.assertEqual(resolved, "3524")

    def test_build_catalog_dataframe_deduplicates_ids(self) -> None:
        snapshot_df = pd.DataFrame(
            [
                {
                    "id_conagua": "3524",
                    "nombre_oficial": "Pedro José Méndez",
                    "estado": "Tamaulipas",
                    "anio": 2026,
                    "mes": 4,
                    "decena": 3,
                },
                {
                    "id_conagua": "3524",
                    "nombre_oficial": "Pedro José Méndez",
                    "estado": "Tamaulipas",
                    "anio": 2026,
                    "mes": 4,
                    "decena": 3,
                },
                {
                    "id_conagua": "1111",
                    "nombre_oficial": "Otra Presa",
                    "estado": "Sonora",
                    "anio": 2026,
                    "mes": 4,
                    "decena": 3,
                },
            ]
        )

        catalog = build_catalog_dataframe(snapshot_df)

        self.assertEqual(len(catalog), 2)
        self.assertIn("id_conagua", catalog.columns)
        self.assertIn("periods_seen_count", catalog.columns)

    def test_build_catalog_dataframe_tracks_first_and_last_seen_periods(self) -> None:
        snapshot_df = pd.DataFrame(
            [
                {
                    "id_conagua": "3524",
                    "nombre_oficial": "Pedro José Méndez",
                    "estado": "Tamaulipas",
                    "anio": 2024,
                    "mes": 1,
                    "decena": 1,
                },
                {
                    "id_conagua": "3524",
                    "nombre_oficial": "Pedro José Méndez",
                    "estado": "Tamaulipas",
                    "anio": 2026,
                    "mes": 4,
                    "decena": 3,
                },
            ]
        )

        catalog = build_catalog_dataframe(snapshot_df)

        self.assertEqual(int(catalog.iloc[0]["periods_seen_count"]), 2)
        self.assertEqual(int(catalog.iloc[0]["first_seen_year"]), 2024)
        self.assertEqual(int(catalog.iloc[0]["first_seen_month"]), 1)
        self.assertEqual(int(catalog.iloc[0]["first_seen_day_block"]), 1)
        self.assertEqual(int(catalog.iloc[0]["last_seen_year"]), 2026)
        self.assertEqual(int(catalog.iloc[0]["last_seen_month"]), 4)
        self.assertEqual(int(catalog.iloc[0]["last_seen_day_block"]), 3)

    def test_filter_snapshot_by_state_matches_accent_insensitive(self) -> None:
        snapshot_df = pd.DataFrame(
            [
                {"id_conagua": "1", "estado": "Nuevo León"},
                {"id_conagua": "2", "estado": "Tamaulipas"},
            ]
        )

        filtered = _filter_snapshot_by_state(snapshot_df, "Nuevo Leon")

        self.assertEqual(filtered["id_conagua"].tolist(), ["1"])

    def test_iter_catalog_periods_caps_current_year_to_published_period(self) -> None:
        periods = _iter_catalog_periods(
            years=[2026, 2025],
            scope="all-available",
            default_period={"year": 2026, "month": 4, "day_block": 3},
        )

        self.assertNotIn((2026, 5, 1), periods)
        self.assertIn((2026, 4, 3), periods)
        self.assertIn((2026, 1, 1), periods)
        self.assertIn((2025, 12, 3), periods)

    def test_iter_forward_periods_covers_same_year_range(self) -> None:
        periods = _iter_forward_periods(
            start_year=2025,
            start_month=1,
            start_day_block=2,
            end_year=2025,
        )

        self.assertEqual(periods[0], (2025, 1, 2))
        self.assertEqual(periods[-1], (2025, 12, 3))
        self.assertEqual(len(periods), 35)

    def test_iter_forward_periods_spans_multiple_years(self) -> None:
        periods = _iter_forward_periods(
            start_year=2024,
            start_month=12,
            start_day_block=3,
            end_year=2025,
        )

        self.assertEqual(periods[0], (2024, 12, 3))
        self.assertEqual(periods[-1], (2025, 12, 3))
        self.assertIn((2025, 1, 1), periods)

    def test_iter_forward_periods_caps_to_published_period(self) -> None:
        periods = _iter_forward_periods(
            start_year=2026,
            start_month=1,
            start_day_block=1,
            end_year=2026,
            cap_period={"year": 2026, "month": 4, "day_block": 3},
        )

        self.assertNotIn((2026, 5, 1), periods)
        self.assertEqual(periods[-1], (2026, 4, 3))

    def test_load_queries_config_enables_period_range_for_presas_periodo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "presas.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "nombre_consulta": "cortes_2025",
                        "tipo_consulta": "presas_periodo",
                        "anio": 2025,
                        "mes": 1,
                        "decena": 1,
                        "anio_final": 2025,
                    }
                ]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)

            queries = load_queries_config(path)

            self.assertEqual(queries[0].range_end_year, 2025)

    def test_load_queries_config_keeps_single_period_when_anio_final_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "presas.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "nombre_consulta": "corte_unico",
                        "tipo_consulta": "presas_periodo",
                        "anio": 2025,
                        "mes": 4,
                        "decena": 3,
                        "anio_final": "",
                    }
                ]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)

            queries = load_queries_config(path)

            self.assertIsNone(queries[0].range_end_year)
            self.assertEqual(queries[0].end_year, 2025)

    def test_load_queries_config_rejects_anio_final_before_anio_for_presas_periodo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "presas.xlsx"
            df = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "nombre_consulta": "rango_invalido",
                        "tipo_consulta": "presas_periodo",
                        "anio": 2026,
                        "mes": 4,
                        "decena": 3,
                        "anio_final": 2025,
                    }
                ]
            )
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)

            with self.assertRaisesRegex(ValueError, "anio_final \\(2025\\) no puede ser menor"):
                load_queries_config(path)


def load_queries_config_from_rows(rows: list[dict[str, object]]):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "presas.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, sheet_name=QUERY_SHEET_NAME, index=False)
            pd.DataFrame(
                [{"id_conagua": "3524", "nombre_oficial": "Pedro José Méndez", "estado": "Tamaulipas"}]
            ).to_excel(
                writer,
                sheet_name=CATALOG_SHEET_NAME,
                index=False,
            )
        return load_queries_config(path)


if __name__ == "__main__":
    unittest.main()
