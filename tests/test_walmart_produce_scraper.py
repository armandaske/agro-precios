import json
import unittest

from src.extract.walmart_produce_scraper import (
    choose_best_record_per_crop,
    extract_next_data,
    extract_search_items,
    item_to_record,
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


if __name__ == "__main__":
    unittest.main()
