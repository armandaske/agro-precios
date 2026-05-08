import unittest
from pathlib import Path

from src.extract.sniim import (
    _append_metadata,
    _extract_site_product_name,
    _normalize_dataframe,
    _parse_results_table_or_raise,
    normalize_column_name,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "sniim_resultado_producto_133_2026-03-03_2026-03-16.html"
)


class SniimParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_normalize_column_name_supports_aliases(self) -> None:
        cases = {
            "Presentaci\u00f3n": "presentacion",
            "Presentaci\u00c3\u00b3n": "presentacion",
            "Precio M\u00edn": "precio_minimo",
            "Precio M\u00c3\u00adn": "precio_minimo",
            "Precio M\u00e1ximo": "precio_maximo",
            "Precio Max": "precio_maximo",
            "Precio Frec": "precio_frecuente",
            "Obs.": "obs",
        }

        for raw_name, expected in cases.items():
            with self.subTest(raw_name=raw_name):
                self.assertEqual(normalize_column_name(raw_name), expected)

    def test_parse_live_fixture_returns_real_results_table(self) -> None:
        parsed = _parse_results_table_or_raise(self.html)
        normalized = _normalize_dataframe(parsed)

        self.assertFalse(normalized.empty)
        self.assertGreater(len(normalized), 300)
        self.assertEqual(
            normalized.columns.tolist(),
            [
                "fecha",
                "presentacion",
                "origen",
                "destino",
                "precio_minimo",
                "precio_maximo",
                "precio_frecuente",
                "obs",
            ],
        )
        self.assertNotEqual(str(normalized.iloc[0]["fecha"]).lower(), "frutas")
        self.assertRegex(str(normalized.iloc[0]["fecha"]), r"^\d{2}/\d{2}/\d{4}$")

    def test_extract_site_product_name_from_fixture(self) -> None:
        self.assertEqual(_extract_site_product_name(self.html), "Aguacate Hass")

    def test_append_metadata_preserves_market_origin_and_destination(self) -> None:
        parsed = _parse_results_table_or_raise(self.html)
        normalized = _normalize_dataframe(parsed)
        enriched = _append_metadata(
            normalized,
            fecha_inicio="2026-03-03",
            fecha_final="2026-03-16",
            producto_id=133,
            producto_nombre_sitio="Aguacate Hass",
            origen_id=-1,
            destino_id=-1,
            precios_por_id=1,
        )

        self.assertIn("producto_nombre_sitio", enriched.columns)
        self.assertIn("origen", enriched.columns)
        self.assertIn("destino", enriched.columns)
        self.assertIn("origen_query", enriched.columns)
        self.assertIn("destino_query", enriched.columns)
        self.assertEqual(str(enriched.iloc[0]["producto_nombre_sitio"]), "Aguacate Hass")
        self.assertNotEqual(str(enriched.iloc[0]["origen"]), "-1")
        self.assertNotEqual(str(enriched.iloc[0]["destino"]), "-1")
        self.assertEqual(str(enriched.iloc[0]["origen_query"]), "-1")
        self.assertEqual(str(enriched.iloc[0]["destino_query"]), "-1")


if __name__ == "__main__":
    unittest.main()
