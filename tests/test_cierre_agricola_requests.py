import unittest

import pandas as pd

from src.extract.cierre_agricola_requests import (
    _extract_report_header_metadata,
    _normalize_report_dataframe,
    _report_content_to_dataframe,
)


class CierreAgricolaRequestsTests(unittest.TestCase):
    def test_extract_report_header_metadata_preserves_crop_label_and_unit(self) -> None:
        html = """
        <html><body>
        <table>
            <tr><td>Producción Agrícola</td></tr>
            <tr><td>Cultivo: Tomate rojo (jitomate) (ton)</td></tr>
        </table>
        </body></html>
        """

        metadata = _extract_report_header_metadata(html)

        self.assertEqual(metadata["cierre_crop_label_raw"], "Tomate rojo (jitomate) (ton)")
        self.assertEqual(metadata["cierre_unit_label"], "ton")

    def test_normalize_report_dataframe_flattens_multilevel_headers(self) -> None:
        df = pd.DataFrame(
            [[1, "Michoacán", 100.0, 90.0, 5.0, 80.0, 0.89, 1234.5, 9876.0]],
            columns=pd.MultiIndex.from_tuples(
                [
                    ("Unnamed: 0_level_0", "Unnamed: 0_level_1"),
                    ("Entidad", "Entidad"),
                    ("Superficie (ha)", "Sembrada"),
                    ("Superficie (ha)", "Cosechada"),
                    ("Superficie (ha)", "Siniestrada"),
                    ("Producción", "Producción"),
                    ("Rendimiento (udm/ha)", "Rendimiento (udm/ha)"),
                    ("PMR ($/udm)", "PMR ($/udm)"),
                    ("Valor Producción (miles de Pesos)", "Valor Producción (miles de Pesos)"),
                ]
            ),
        )

        normalized = _normalize_report_dataframe(df)

        self.assertEqual(
            normalized.columns.tolist(),
            [
                "numero",
                "entidad",
                "superficie_sembrada_ha",
                "superficie_cosechada_ha",
                "superficie_siniestrada_ha",
                "produccion",
                "rendimiento_udm_ha",
                "pmr_mxn_udm",
                "valor_produccion_miles_pesos",
            ],
        )

    def test_report_content_to_dataframe_appends_metadata_columns(self) -> None:
        html = """
        <html><body>
        <table>
            <tr><td>Producción Agrícola</td></tr>
            <tr><td>Cultivo: Aguacate (ton)</td></tr>
        </table>
        <table border="1">
            <tr>
                <th>Entidad</th>
                <th>Producción</th>
                <th>PMR ($/udm)</th>
            </tr>
            <tr>
                <td>Michoacán</td>
                <td>100</td>
                <td>25.5</td>
            </tr>
        </table>
        </body></html>
        """.encode("utf-8")

        normalized = _report_content_to_dataframe(html, year="2024", crop="Aguacate")

        self.assertIn("cierre_crop_label_raw", normalized.columns)
        self.assertIn("cierre_unit_label", normalized.columns)
        self.assertIn("cierre_crop_name", normalized.columns)
        self.assertIn("query_year", normalized.columns)
        self.assertEqual(str(normalized.iloc[0]["cierre_crop_label_raw"]), "Aguacate (ton)")
        self.assertEqual(str(normalized.iloc[0]["cierre_unit_label"]), "ton")
        self.assertEqual(str(normalized.iloc[0]["cierre_crop_name"]), "Aguacate")
        self.assertEqual(int(normalized.iloc[0]["query_year"]), 2024)


if __name__ == "__main__":
    unittest.main()
