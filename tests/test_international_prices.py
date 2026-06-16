import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_international_price_features import (
    build_international_price_features,
    default_proxy_config,
)
from src.extract.fred_public_csv import normalize_fred_dexmxus
from src.extract.imf_commodities import normalize_imf_commodity_file
from src.extract.usda_specialty_crops_files import normalize_usda_specialty_crop_file
from src.extract.world_bank_commodities import normalize_world_bank_prices


class InternationalPriceTests(unittest.TestCase):
    def test_world_bank_parser_normalizes_monthly_prices(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pink.xlsx"
            rows = [[pd.NA] * 3 for _ in range(8)]
            rows[4] = [pd.NA, "Maize", "Banana, US"]
            rows[5] = [pd.NA, "($/mt)", "($/kg)"]
            rows[6] = ["2026M01", 200.0, 1.1]
            rows[7] = ["2026M02", 210.0, 1.2]
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame(rows).to_excel(writer, sheet_name="Monthly Prices", header=False, index=False)

            normalized = normalize_world_bank_prices(path)

            self.assertEqual(len(normalized), 4)
            self.assertIn("Maize", set(normalized["serie"]))
            self.assertEqual(str(normalized.iloc[0]["fuente"]), "world_bank")

    def test_fred_parser_normalizes_public_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dexmxus.csv"
            path.write_text("observation_date,DEXMXUS\n2026-01-01,17.0\n2026-01-02,.\n", encoding="utf-8")

            normalized = normalize_fred_dexmxus(path)

            self.assertEqual(len(normalized), 1)
            self.assertEqual(str(normalized.iloc[0]["serie"]), "DEXMXUS")
            self.assertEqual(float(normalized.iloc[0]["precio_original"]), 17.0)

    def test_imf_and_usda_file_parsers_accept_local_public_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            imf_path = root / "imf.csv"
            usda_path = root / "usda.csv"
            imf_path.write_text("date,commodity,value\n2026-01-01,Maize,200\n", encoding="utf-8")
            usda_path.write_text(
                "date,commodity,low_price,high_price,unit\n2026-01-03,avocado hass,40,44,carton\n",
                encoding="utf-8",
            )

            imf = normalize_imf_commodity_file(imf_path)
            usda = normalize_usda_specialty_crop_file(usda_path)

            self.assertEqual(str(imf.iloc[0]["fuente"]), "imf")
            self.assertEqual(float(usda.iloc[0]["precio_original"]), 42.0)
            self.assertEqual(str(usda.iloc[0]["fuente"]), "usda_ams")

    def test_feature_builder_applies_proxy_config_fx_and_diagnostic_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "products.xlsx"
            raw_root = root / "raw"
            (raw_root / "world_bank").mkdir(parents=True)
            (raw_root / "fred").mkdir(parents=True)
            (raw_root / "usda_ams").mkdir(parents=True)

            proxies = pd.DataFrame(
                [
                    {
                        "activo": True,
                        "producto_canonico": "Aguacate",
                        "proxy_id": "usda_ams_aguacate",
                        "fuente": "usda_ams",
                        "serie": "avocado",
                        "tipo_proxy": "fuerte",
                        "uso_modelo": "feature",
                        "frecuencia": "diaria",
                        "moneda": "USD",
                        "unidad_origen": "carton",
                        "nota_metodologica": "fixture",
                    },
                    {
                        "activo": True,
                        "producto_canonico": "Elote",
                        "proxy_id": "world_bank_maize",
                        "fuente": "world_bank",
                        "serie": "Maize",
                        "tipo_proxy": "medio",
                        "uso_modelo": "diagnostico_only",
                        "frecuencia": "mensual",
                        "moneda": "USD",
                        "unidad_origen": "$/mt",
                        "nota_metodologica": "fixture",
                    },
                ]
            )
            with pd.ExcelWriter(config_path, engine="openpyxl") as writer:
                pd.DataFrame([{"activo": True, "producto_canonico": "Aguacate"}]).to_excel(
                    writer,
                    sheet_name="productos",
                    index=False,
                )
                proxies.to_excel(writer, sheet_name="proxies_internacionales", index=False)

            (raw_root / "fred" / "dexmxus.csv").write_text(
                "observation_date,DEXMXUS\n2026-01-01,17.0\n2026-01-31,18.0\n",
                encoding="utf-8",
            )
            (raw_root / "usda_ams" / "usda.csv").write_text(
                "date,commodity,price,unit\n2026-01-03,avocado hass,2.0,kg\n",
                encoding="utf-8",
            )
            wb_path = raw_root / "world_bank" / "pink.xlsx"
            rows = [[pd.NA] * 2 for _ in range(7)]
            rows[4] = [pd.NA, "Maize"]
            rows[5] = [pd.NA, "($/mt)"]
            rows[6] = ["2026M01", 200.0]
            with pd.ExcelWriter(wb_path, engine="openpyxl") as writer:
                pd.DataFrame(rows).to_excel(writer, sheet_name="Monthly Prices", header=False, index=False)

            features, loaded_config = build_international_price_features(config_path, raw_root)

            self.assertEqual(len(loaded_config), 2)
            self.assertIn("usda_ams_aguacate", set(features["proxy_id"]))
            aguacate = features[features["proxy_id"].eq("usda_ams_aguacate")].iloc[0]
            self.assertEqual(str(aguacate["producto_canonico"]), "aguacate")
            self.assertAlmostEqual(float(aguacate["precio_mxn"]), 34.0)
            maize = features[features["proxy_id"].eq("world_bank_maize")].iloc[0]
            self.assertEqual(str(maize["uso_modelo"]), "diagnostico_only")
            self.assertGreater(pd.Timestamp(maize["fecha_disponible"]), pd.Timestamp(maize["fecha"]))

    def test_default_proxy_config_contains_no_token_based_sources(self) -> None:
        config = default_proxy_config()
        self.assertNotIn("banxico", set(config["fuente"].astype(str).str.casefold()))
        self.assertIn("fred", set(config["fuente"].astype(str).str.casefold()))


if __name__ == "__main__":
    unittest.main()
