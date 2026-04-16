import unittest

import pandas as pd

from src.extract.cierre_agricola_requests import _normalize_report_dataframe


class CierreAgricolaRequestsTests(unittest.TestCase):
    def test_normalize_report_dataframe_flattens_multilevel_headers(self) -> None:
        df = pd.DataFrame(
            [[1, "MichoacÃ¡n", 100.0, 90.0, 5.0, 80.0, 0.89, 1234.5, 9876.0]],
            columns=pd.MultiIndex.from_tuples(
                [
                    ("Unnamed: 0_level_0", "Unnamed: 0_level_1"),
                    ("Entidad", "Entidad"),
                    ("Superficie (ha)", "Sembrada"),
                    ("Superficie (ha)", "Cosechada"),
                    ("Superficie (ha)", "Siniestrada"),
                    ("ProducciÃ³n", "ProducciÃ³n"),
                    ("Rendimiento (udm/ha)", "Rendimiento (udm/ha)"),
                    ("PMR ($/udm)", "PMR ($/udm)"),
                    ("Valor ProducciÃ³n (miles de Pesos)", "Valor ProducciÃ³n (miles de Pesos)"),
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


if __name__ == "__main__":
    unittest.main()
