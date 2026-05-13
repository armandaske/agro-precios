import unittest

import pandas as pd

from src.extract.avance_agricola_requests import (
    _extract_report_header_metadata,
    _normalize_report_dataframe,
    _report_content_to_dataframe,
)


class AvanceAgricolaRequestsTests(unittest.TestCase):
    def test_extract_report_header_metadata_preserves_crop_unit_and_cutoff(self) -> None:
        html = """
        <html><body>
        <div>
            <p><strong>Cultivo:</strong> Aguacate (ton)</p>
            <p>Situación al 28 de febrero de 2026</p>
        </div>
        </body></html>
        """

        metadata = _extract_report_header_metadata(html)

        self.assertEqual(metadata["avance_crop_label_raw"], "Aguacate (ton)")
        self.assertEqual(metadata["avance_unit_label"], "ton")
        self.assertEqual(metadata["report_cutoff_label"], "Situación al 28 de febrero de 2026")

    def test_normalize_report_dataframe_flattens_multilevel_headers(self) -> None:
        df = pd.DataFrame(
            [[1, "Michoacán", 100.0, 90.0, 5.0, 80.0, 0.89]],
            columns=pd.MultiIndex.from_tuples(
                [
                    ("Unnamed: 0_level_0", "Unnamed: 0_level_1"),
                    ("Entidad", "Entidad"),
                    ("Superficie (ha)", "Sembrada"),
                    ("Superficie (ha)", "Cosechada"),
                    ("Superficie (ha)", "Siniestrada"),
                    ("Producción", "Producción"),
                    ("Rendimiento (udm/ha)", "Rendimiento (udm/ha)"),
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
            ],
        )

    def test_report_content_to_dataframe_appends_metadata_columns(self) -> None:
        html = """
        <html><body>
        <div>
            <p><strong>Cultivo:</strong> Aguacate (ton)</p>
            <p>Situación al 28 de febrero de 2026</p>
        </div>
        <table border="1">
            <tr>
                <th>Entidad</th>
                <th>Producción</th>
                <th>Rendimiento (udm/ha)</th>
            </tr>
            <tr>
                <td>Michoacán</td>
                <td>100</td>
                <td>25.5</td>
            </tr>
        </table>
        </body></html>
        """.encode("utf-8")

        normalized = _report_content_to_dataframe(
            html,
            year="2026",
            month_value="2",
            month_label="Febrero",
            crop="Aguacate",
        )

        self.assertIn("avance_crop_label_raw", normalized.columns)
        self.assertIn("avance_unit_label", normalized.columns)
        self.assertIn("avance_crop_name", normalized.columns)
        self.assertIn("query_year", normalized.columns)
        self.assertIn("query_month", normalized.columns)
        self.assertIn("query_month_label", normalized.columns)
        self.assertEqual(str(normalized.iloc[0]["avance_crop_label_raw"]), "Aguacate (ton)")
        self.assertEqual(str(normalized.iloc[0]["avance_unit_label"]), "ton")
        self.assertEqual(str(normalized.iloc[0]["avance_crop_name"]), "Aguacate")
        self.assertEqual(int(normalized.iloc[0]["query_year"]), 2026)
        self.assertEqual(int(normalized.iloc[0]["query_month"]), 2)
        self.assertEqual(str(normalized.iloc[0]["query_month_label"]), "Febrero")


if __name__ == "__main__":
    unittest.main()
