import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.normalize_company_avance_history import (
    build_historical_avance_frame,
    trim_trailing_zero_suffix,
    write_historical_avance_outputs,
)


class NormalizeCompanyAvanceHistoryTests(unittest.TestCase):
    def test_trim_trailing_zero_suffix_marks_terminal_zeros_as_missing(self) -> None:
        values = [0, 4, 9, 9, 0, 0]
        trimmed = trim_trailing_zero_suffix(values)
        self.assertEqual(trimmed[:4], [0, 4, 9, 9])
        self.assertTrue(pd.isna(trimmed[4]))
        self.assertTrue(pd.isna(trimmed[5]))

    def test_build_historical_frame_maps_and_prioritizes_company_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "company.csv"
            pd.DataFrame(
                [
                    {
                        "tipo": "SIEMBRA",
                        "cultivo": "TOMATE ROJO",
                        "anio": 2024,
                        "estados": "QUERETARO",
                        "pre_oct": 0,
                        "pre_nov": 0,
                        "pre_dec": 0,
                        "jan": 10,
                        "feb": 20,
                        "mar": 30,
                        "apr": 40,
                        "may": 50,
                        "jun": 60,
                        "jul": 70,
                        "aug": 80,
                        "sep": 90,
                        "oct": 100,
                        "nov": 110,
                        "dec": 120,
                        "pos_jan": 0,
                        "pos_feb": 0,
                        "pos_mar": 0,
                    },
                    {
                        "tipo": "SIEMBRA",
                        "cultivo": "TOMATE ROJO (JITOMATE)",
                        "anio": 2024,
                        "estados": "QUERETARO",
                        "pre_oct": 0,
                        "pre_nov": 0,
                        "pre_dec": 0,
                        "jan": 11,
                        "feb": 21,
                        "mar": 31,
                        "apr": 41,
                        "may": 51,
                        "jun": 61,
                        "jul": 71,
                        "aug": 81,
                        "sep": 91,
                        "oct": 101,
                        "nov": 111,
                        "dec": 121,
                        "pos_jan": 0,
                        "pos_feb": 0,
                        "pos_mar": 0,
                    },
                    {
                        "tipo": "COSECHA",
                        "cultivo": "MAIZ GRANO",
                        "anio": 2023,
                        "estados": "MICHOACAN",
                        "pre_oct": 0,
                        "pre_nov": 0,
                        "pre_dec": 0,
                        "jan": 0,
                        "feb": 5,
                        "mar": 10,
                        "apr": 15,
                        "may": 20,
                        "jun": 25,
                        "jul": 30,
                        "aug": 35,
                        "sep": 40,
                        "oct": 45,
                        "nov": 45,
                        "dec": 0,
                        "pos_jan": 0,
                        "pos_feb": 0,
                        "pos_mar": 0,
                    },
                    {
                        "tipo": "SIEMBRA",
                        "cultivo": "CHILE VERDE",
                        "anio": 2024,
                        "estados": "ESTADO",
                        "pre_oct": 0,
                        "pre_nov": 0,
                        "pre_dec": 0,
                        "jan": 0,
                        "feb": 0,
                        "mar": 0,
                        "apr": 0,
                        "may": 0,
                        "jun": 0,
                        "jul": 0,
                        "aug": 0,
                        "sep": 0,
                        "oct": 0,
                        "nov": 0,
                        "dec": 0,
                        "pos_jan": 0,
                        "pos_feb": 0,
                        "pos_mar": 0,
                    },
                ]
            ).to_csv(path, index=False, encoding="utf-8-sig")

            frame = build_historical_avance_frame(path, years={2023, 2024})

        tomato_jan = frame[
            (frame["cultivo_avance_agricola"] == "Tomate rojo")
            & (frame["anio_consulta"] == 2024)
            & (frame["mes_consulta"] == 1)
            & (frame["entidad_entidad"] == "Querétaro")
        ]
        self.assertEqual(len(tomato_jan), 1)
        self.assertEqual(float(tomato_jan.iloc[0]["superficie_sembrada_ha"]), 11.0)
        self.assertEqual(
            str(tomato_jan.iloc[0]["cultivo_avance_agricola_original"]),
            "TOMATE ROJO (JITOMATE)",
        )

        elote_dec = frame[
            (frame["cultivo_avance_agricola"] == "Elote")
            & (frame["anio_consulta"] == 2023)
            & (frame["mes_consulta"] == 12)
            & (frame["entidad_entidad"] == "Michoacán")
        ]
        self.assertEqual(len(elote_dec), 0)

        elote_nov = frame[
            (frame["cultivo_avance_agricola"] == "Elote")
            & (frame["anio_consulta"] == 2023)
            & (frame["mes_consulta"] == 11)
            & (frame["entidad_entidad"] == "Michoacán")
        ]
        self.assertEqual(float(elote_nov.iloc[0]["superficie_cosechada_ha"]), 45.0)
        self.assertFalse(frame["entidad_entidad"].eq("ESTADO").any())

    def test_write_outputs_creates_crop_year_workbooks(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "entidad_entidad": "Querétaro",
                    "superficie_sembrada_ha": 12,
                    "superficie_cosechada_ha": pd.NA,
                    "superficie_siniestrada_ha": pd.NA,
                    "produccion_produccion": pd.NA,
                    "rendimiento_udm_ha_rendimiento_udm_ha": pd.NA,
                    "cultivo_avance_agricola_original": "AGUACATE",
                    "unidad_avance_agricola": "ha",
                    "cultivo_avance_agricola": "Aguacate",
                    "anio_consulta": 2023,
                    "mes_consulta": 1,
                    "mes_consulta_nombre": "Enero",
                    "situacion_corte": "Historico interno empresarial al cierre de Enero de 2023",
                    "nombre_fuente": "historico_empresa_siembra_cosecha",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = write_historical_avance_outputs(frame, Path(temp_dir))
            self.assertEqual(summary["files_written"], 1)
            output_path = Path(temp_dir) / "aguacate_2023_historico_empresa.xlsx"
            self.assertTrue(output_path.exists())
            written = pd.read_excel(output_path)
            self.assertIn("numero", written.columns)
            self.assertEqual(float(written.iloc[0]["superficie_sembrada_ha"]), 12.0)


if __name__ == "__main__":
    unittest.main()
