import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.extract.walmart_produce_scraper import (
    choose_best_record_per_crop,
    choose_best_records,
    extract_next_data,
    extract_search_items,
    item_to_record,
    save_output,
)


def make_search_html(items):
    payload = {
        "props": {
            "pageProps": {
                "initialData": {
                    "searchResult": {
                        "itemStacks": [
                            {
                                "items": items,
                            }
                        ]
                    }
                }
            }
        }
    }
    return (
        "<html><head></head><body>"
        f"<script id=\"__NEXT_DATA__\" type=\"application/json\">{json.dumps(payload)}</script>"
        "</body></html>"
    )


class WalmartProduceScraperTests(unittest.TestCase):
    def test_extract_next_data_and_items_from_search_page(self) -> None:
        html = make_search_html(
            [
                {
                    "__typename": "Product",
                    "name": "Aguacate Hass por kilo",
                    "canonicalUrl": "/ip/aguacate-hass-por-kilo/00000000004225",
                    "salesUnitType": "EACH_WEIGHT",
                    "averageWeight": 0.265,
                    "priceInfo": {
                        "linePrice": "$49.90/kg",
                        "itemPrice": "",
                        "wasPrice": "",
                        "savingsAmt": 0,
                    },
                },
                {
                    "__typename": "Advertisement",
                    "name": "Ignore me",
                },
            ]
        )

        next_data = extract_next_data(html)
        items = extract_search_items(next_data)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Aguacate Hass por kilo")

    def test_item_to_record_parses_weighted_and_promotional_products(self) -> None:
        weighted = {
            "name": "Aguacate Hass por kilo",
            "canonicalUrl": "/ip/aguacate-hass-por-kilo/00000000004225",
            "salesUnitType": "EACH_WEIGHT",
            "averageWeight": 0.265,
            "priceInfo": {
                "linePrice": "$49.90/kg",
                "itemPrice": "",
                "wasPrice": "",
                "savingsAmt": 0,
            },
        }
        promo = {
            "name": "Jitomate saladet por kilo",
            "canonicalUrl": "/ip/jitomate-saladet-por-kilo/00000000004087",
            "salesUnitType": "EACH_WEIGHT",
            "averageWeight": 0.106,
            "priceInfo": {
                "linePrice": "$49.00/kg",
                "itemPrice": "$56.00/kg",
                "wasPrice": "$56.00/kg",
                "savingsAmt": 7,
            },
        }

        weighted_record = item_to_record(weighted, "aguacate")
        promo_record = item_to_record(promo, "jitomate")

        self.assertIsNotNone(weighted_record)
        self.assertEqual(weighted_record["product_canonical"], "aguacate")
        self.assertEqual(weighted_record["price_mxn"], 49.9)
        self.assertEqual(weighted_record["unit_raw"], "kg")
        self.assertEqual(weighted_record["estimated_price_per_kg_mxn"], 49.9)
        self.assertFalse(weighted_record["promo_flag"])

        self.assertIsNotNone(promo_record)
        self.assertEqual(promo_record["product_canonical"], "tomate")
        self.assertEqual(promo_record["price_mxn"], 49.0)
        self.assertEqual(promo_record["old_price_mxn"], 56.0)
        self.assertTrue(promo_record["promo_flag"])

    def test_choose_best_record_per_crop_prefers_direct_kg_listing(self) -> None:
        records = [
            {
                "product_canonical": "aguacate",
                "product_raw": "Aguacate Hass por kilo",
                "source_query": "aguacate",
                "price_mxn": 49.9,
                "promo_flag": False,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 49.9,
                "fresh_produce_flag": True,
            },
            {
                "product_canonical": "aguacate",
                "product_raw": "Aguacate hass orgánico Marketside en malla 800 g",
                "source_query": "aguacate",
                "price_mxn": 150.0,
                "promo_flag": False,
                "unit_raw": "g_pack",
                "estimated_price_per_kg_mxn": 187.5,
                "fresh_produce_flag": True,
            },
            {
                "product_canonical": "tomate",
                "product_raw": "Jitomate saladet por kilo",
                "source_query": "jitomate",
                "price_mxn": 49.0,
                "promo_flag": True,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 49.0,
                "fresh_produce_flag": True,
            },
        ]

        best = choose_best_record_per_crop(records)

        self.assertEqual(len(best), 2)
        best_by_crop = {record["product_canonical"]: record for record in best}
        self.assertEqual(best_by_crop["aguacate"]["product_raw"], "Aguacate Hass por kilo")
        self.assertEqual(best_by_crop["tomate"]["product_raw"], "Jitomate saladet por kilo")

    def test_item_to_record_supports_configured_product_outside_hardcoded_catalog(self) -> None:
        item = {
            "name": "Manzana golden por kilo",
            "canonicalUrl": "/ip/manzana-golden-por-kilo/00000000000001",
            "salesUnitType": "EACH_WEIGHT",
            "averageWeight": 0.2,
            "priceInfo": {
                "linePrice": "$39.90/kg",
                "itemPrice": "",
                "wasPrice": "",
                "savingsAmt": 0,
            },
        }

        record = item_to_record(item, "manzana", configured_product="manzana")

        self.assertIsNotNone(record)
        self.assertEqual(record["product_canonical"], "manzana")
        self.assertIsNone(record["product_inferred"])
        self.assertEqual(record["price_mxn"], 39.9)

    def test_choose_best_records_supports_custom_product_keys(self) -> None:
        records = [
            {
                "product_canonical": "manzana",
                "product_raw": "Manzana golden por kilo",
                "source_query": "manzana",
                "price_mxn": 39.9,
                "promo_flag": False,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 39.9,
                "fresh_produce_flag": True,
            },
            {
                "product_canonical": "manzana",
                "product_raw": "Manzana golden en bolsa 1 kg",
                "source_query": "apple",
                "price_mxn": 45.0,
                "promo_flag": False,
                "unit_raw": "g_pack",
                "estimated_price_per_kg_mxn": 45.0,
                "fresh_produce_flag": True,
            },
        ]

        best = choose_best_records(records, ["manzana"], {"manzana": ["manzana", "apple"]})

        self.assertEqual(len(best), 1)
        self.assertEqual(best[0]["product_raw"], "Manzana golden por kilo")

    def test_save_output_exports_spanish_headers(self) -> None:
        records = [
            {
                "scraped_at_utc": "2026-04-08T12:00:00+00:00",
                "source": "walmart_mx",
                "source_page": "https://www.walmart.com.mx/ip/aguacate",
                "source_query": "aguacate",
                "product_raw": "Aguacate Hass por kilo",
                "product_canonical": "aguacate",
                "product_inferred": "aguacate",
                "price_mxn": 49.9,
                "old_price_mxn": None,
                "promo_flag": False,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 49.9,
                "presentation_weight_kg": None,
                "sales_unit_type": "EACH_WEIGHT",
                "average_weight_kg": 0.265,
                "brand_raw": "Frutas y verduras frescas",
                "category_path": "Frutas y Verduras > Frutas",
                "fresh_produce_flag": True,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "walmart.csv"
            save_output(records, str(output_path), "csv")

            exported = pd.read_csv(output_path)
            self.assertIn("fecha_extraccion_utc", exported.columns)
            self.assertIn("producto_original", exported.columns)
            self.assertIn("producto_canonico", exported.columns)
            self.assertIn("esta_en_promocion", exported.columns)


if __name__ == "__main__":
    unittest.main()
