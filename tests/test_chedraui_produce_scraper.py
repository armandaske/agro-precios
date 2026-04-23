import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.extract.chedraui_produce_scraper import (
    collect_search_records,
    choose_best_record_per_crop,
    canonical_crop,
    extract_search_items,
    item_to_record,
    save_output,
)


def make_supermercado_html(items):
    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": items,
    }
    return (
        "<html><body>"
        f"<script type=\"application/ld+json\">{json.dumps(payload)}</script>"
        "</body></html>"
    )


class ChedrauiProduceScraperTests(unittest.TestCase):
    def test_extract_search_items_from_json_ld(self) -> None:
        html = make_supermercado_html(
            [
                {
                    "@type": "Product",
                    "name": "Aguacate Hass por Kg",
                    "url": "/aguacate-hass-por-kg/p",
                    "offers": {"price": "59.5", "highPrice": "69.0"},
                },
                {
                    "@type": "Product",
                    "name": "Jitomate Saladet por Kg",
                    "url": "/jitomate-saladet-por-kg/p",
                    "offers": {"price": "34.9"},
                },
            ]
        )

        items = extract_search_items(html)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "Aguacate Hass por Kg")

    def test_item_to_record_parses_prices_and_units(self) -> None:
        item = {
            "name": "Aguacate Hass por Kg",
            "url": "/aguacate-hass-por-kg/p",
            "brand": "Chedraui",
            "offers": {"price": "59.5", "highPrice": "69.0"},
        }

        record = item_to_record(item, "aguacate")

        self.assertIsNotNone(record)
        self.assertEqual(record["product_canonical"], "aguacate")
        self.assertEqual(record["price_mxn"], 59.5)
        self.assertEqual(record["old_price_mxn"], 69.0)
        self.assertEqual(record["unit_raw"], "kg")
        self.assertTrue(record["promo_flag"])

    def test_item_to_record_uses_high_price_as_current_for_weighted_aggregate_offer(self) -> None:
        item = {
            "name": "Tomate Saladet por kg",
            "url": "/tomate-saladet-por-kg/p",
            "brand": "Chedraui",
            "offers": {
                "@type": "AggregateOffer",
                "lowPrice": 8.85,
                "highPrice": 59.0,
                "offers": [{"@type": "Offer", "price": 8.85}],
            },
        }

        record = item_to_record(item, "tomate")

        self.assertIsNotNone(record)
        self.assertEqual(record["price_mxn"], 59.0)
        self.assertIsNone(record["old_price_mxn"])
        self.assertFalse(record["promo_flag"])

    def test_item_to_record_prefers_vtex_offer_prices_when_available(self) -> None:
        item = {
            "name": "Tomate Saladet por kg",
            "url": "/tomate-saladet-por-kg/p",
            "brand": "Chedraui",
            "offers": {
                "@type": "AggregateOffer",
                "lowPrice": 8.85,
                "highPrice": 59.0,
                "offers": [{"@type": "Offer", "price": 8.85}],
            },
            "items": [
                {
                    "sellers": [
                        {
                            "commertialOffer": {
                                "Price": 59.0,
                                "ListPrice": 72.0,
                                "PriceWithoutDiscount": 72.0,
                            }
                        }
                    ]
                }
            ],
        }

        record = item_to_record(item, "tomate")

        self.assertIsNotNone(record)
        self.assertEqual(record["price_mxn"], 59.0)
        self.assertEqual(record["old_price_mxn"], 72.0)
        self.assertTrue(record["promo_flag"])

    def test_choose_best_record_per_crop_prefers_kg_listing(self) -> None:
        records = [
            {
                "product_canonical": "aguacate",
                "product_raw": "Aguacate Hass por Kg",
                "source_query": "aguacate",
                "price_mxn": 59.5,
                "promo_flag": False,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 59.5,
            },
            {
                "product_canonical": "aguacate",
                "product_raw": "Aguacate Hass enmallado 800 g",
                "source_query": "aguacate",
                "price_mxn": 70,
                "promo_flag": False,
                "unit_raw": "g_pack",
                "estimated_price_per_kg_mxn": 87.5,
            },
        ]

        best = choose_best_record_per_crop(records)

        self.assertEqual(len(best), 1)
        self.assertEqual(best[0]["product_raw"], "Aguacate Hass por Kg")

    def test_canonical_crop_does_not_classify_papaya_as_papa(self) -> None:
        self.assertIsNone(canonical_crop("Papaya Maradol por kg"))
        self.assertEqual(canonical_crop("Papa blanca por kg"), "papa")
        self.assertEqual(canonical_crop("Chile Jalapeño por kg"), "chile_jalapeno")
        self.assertEqual(canonical_crop("Limón sin Semilla por Kg"), "limon")

    def test_collect_search_records_filters_out_papaya_for_papa_query(self) -> None:
        html = make_supermercado_html(
            [
                {
                    "@type": "Product",
                    "name": "Papaya Maradol por Kg",
                    "url": "/papaya-maradol-por-kg/p",
                    "offers": {"price": "32.5"},
                },
                {
                    "@type": "Product",
                    "name": "Papa blanca por Kg",
                    "url": "/papa-blanca-por-kg/p",
                    "offers": {"price": "41.9"},
                },
            ]
        )

        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                class Response:
                    text = html

                    @staticmethod
                    def raise_for_status():
                        return None

                return Response()

        records = collect_search_records(
            session=FakeSession(),
            search_terms={"papa": ["papa"]},
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["product_raw"], "Papa blanca por Kg")
        self.assertEqual(records[0]["product_canonical"], "papa")

    def test_collect_search_records_uses_api_results_when_storefront_results_are_generic(self) -> None:
        generic_html = make_supermercado_html(
            [
                {
                    "@type": "Product",
                    "name": "Tomate Saladet por Kg",
                    "url": "/tomate-saladet-por-kg/p",
                    "offers": {"price": "34.9"},
                }
            ]
        )
        api_payload = json.dumps(
            {
                "products": [
                    {
                        "productName": "Chile Jalapeño por Kg",
                        "link": "/chile-jalapeno-por-kg/p",
                        "brand": "Chedraui",
                        "items": [
                            {
                                "sellers": [
                                    {
                                        "commertialOffer": {
                                            "Price": 49.9,
                                            "ListPrice": 59.9,
                                        }
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        )

        with patch(
            "src.extract.chedraui_produce_scraper.build_search_urls",
            return_value=["https://example.test/storefront", "https://example.test/api"],
        ), patch(
            "src.extract.chedraui_produce_scraper.fetch_html",
            side_effect=[generic_html, api_payload],
        ):
            records = collect_search_records(search_terms={"chile_jalapeno": ["jalapeno"]})

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["product_raw"], "Chile Jalapeño por Kg")
        self.assertEqual(records[0]["product_canonical"], "chile_jalapeno")
        self.assertEqual(records[0]["unit_raw"], "kg")

    def test_save_output_exports_spanish_headers(self) -> None:
        records = [
            {
                "scraped_at_utc": "2026-04-08T12:00:00+00:00",
                "source": "chedraui_mx",
                "source_page": "https://www.chedraui.com.mx/aguacate",
                "source_query": "aguacate",
                "product_raw": "Aguacate Hass por Kg",
                "product_canonical": "aguacate",
                "product_inferred": "aguacate",
                "price_mxn": 59.5,
                "old_price_mxn": 69.0,
                "promo_flag": True,
                "unit_raw": "kg",
                "estimated_price_per_kg_mxn": 59.5,
                "presentation_weight_kg": None,
                "brand_raw": "Chedraui",
                "category_path": "",
                "fresh_produce_flag": True,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "chedraui.csv"
            save_output(records, str(output_path), "csv")

            exported = pd.read_csv(output_path)
            self.assertIn("fecha_extraccion_utc", exported.columns)
            self.assertIn("producto_original", exported.columns)
            self.assertIn("producto_canonico", exported.columns)
            self.assertIn("esta_en_promocion", exported.columns)


if __name__ == "__main__":
    unittest.main()
