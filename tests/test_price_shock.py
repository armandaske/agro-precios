import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.analysis.price_shock import (
    build_margin_anomalies,
    build_price_product_market_features,
    build_weekly_price_comparison,
    run_price_shock_pipeline,
    write_price_report,
)


class PriceShockFeatureTests(unittest.TestCase):
    def test_builds_daily_lags_targets_and_margin_anomalies(self) -> None:
        dates = pd.date_range("2026-01-01", periods=40, freq="D")
        wholesale = pd.DataFrame(
            [
                {
                    "fecha": current_date,
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 40 + index,
                    "precio_minimo": 38 + index,
                    "precio_maximo": 42 + index,
                }
                for index, current_date in enumerate(dates)
            ]
        )
        spreads = pd.DataFrame(
            {
                "fecha": dates,
                "cultivo_canonico": ["aguacate"] * len(dates),
                "precio_mayoreo": [40 + index for index in range(len(dates))],
                "precio_walmart": [60 + index for index in range(len(dates))],
                "spread_walmart": [0.5] * 39 + [3.0],
                "precio_chedraui": [58 + index for index in range(len(dates))],
                "spread_chedraui": [0.45] * len(dates),
            }
        )
        features = build_price_product_market_features(
            wholesale,
            spreads,
            horizons=(7,),
        )
        self.assertEqual(float(features.iloc[7]["precio_lag_7"]), 40)
        self.assertEqual(float(features.iloc[0]["objetivo_precio_h7"]), 47)

        anomalies = build_margin_anomalies(spreads)
        self.assertFalse(anomalies.empty)
        self.assertIn("puntaje_anomalia", anomalies.columns)

    def test_international_features_merge_only_model_features(self) -> None:
        dates = pd.date_range("2026-01-01", periods=15, freq="D")
        wholesale = pd.DataFrame(
            [
                {
                    "fecha": current_date,
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 40 + index,
                    "precio_minimo": 38 + index,
                    "precio_maximo": 42 + index,
                }
                for index, current_date in enumerate(dates)
            ]
        )
        spreads = pd.DataFrame(
            {
                "fecha": dates,
                "cultivo_canonico": ["aguacate"] * len(dates),
                "precio_mayoreo": [40 + index for index in range(len(dates))],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "international.parquet"
            pd.DataFrame(
                [
                    {
                        "fecha": "2026-01-01",
                        "fecha_disponible": "2026-01-01",
                        "producto_canonico": "aguacate",
                        "proxy_id": "fx_usdmxn",
                        "valor_modelo": 17.0,
                        "cambio_1_periodo": 0.01,
                        "cambio_3_periodos": 0.03,
                        "zscore_12_periodos": 0.5,
                        "uso_modelo": "feature",
                    },
                    {
                        "fecha": "2026-01-01",
                        "fecha_disponible": "2026-01-01",
                        "producto_canonico": "aguacate",
                        "proxy_id": "world_bank_orange",
                        "valor_modelo": 2.0,
                        "cambio_1_periodo": 0.02,
                        "cambio_3_periodos": 0.04,
                        "zscore_12_periodos": 0.7,
                        "uso_modelo": "diagnostico_only",
                    },
                ]
            ).to_parquet(path, index=False)

            features = build_price_product_market_features(
                wholesale,
                spreads,
                international_features_path=path,
                horizons=(7,),
            )

        self.assertIn("intl_fx_usdmxn_valor_modelo", features.columns)
        self.assertNotIn("intl_world_bank_orange_valor_modelo", features.columns)

    def test_build_weekly_comparison_keeps_retail_unique_and_computes_ranges(self) -> None:
        wholesale = pd.DataFrame(
            [
                {
                    "fecha": pd.Timestamp("2026-01-05"),
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 10.0,
                    "precio_minimo": 10.0,
                    "precio_maximo": 10.0,
                },
                {
                    "fecha": pd.Timestamp("2026-01-05"),
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado B",
                    "origen": "Jalisco",
                    "precio_frecuente": 20.0,
                    "precio_minimo": 20.0,
                    "precio_maximo": 20.0,
                },
                {
                    "fecha": pd.Timestamp("2026-01-06"),
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 12.0,
                    "precio_minimo": 12.0,
                    "precio_maximo": 12.0,
                },
                {
                    "fecha": pd.Timestamp("2026-01-06"),
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado B",
                    "origen": "Jalisco",
                    "precio_frecuente": 18.0,
                    "precio_minimo": 18.0,
                    "precio_maximo": 18.0,
                },
                {
                    "fecha": pd.Timestamp("2026-01-12"),
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "origen": "Michoacan",
                    "precio_frecuente": 14.0,
                    "precio_minimo": 14.0,
                    "precio_maximo": 14.0,
                },
                {
                    "fecha": pd.Timestamp("2026-01-12"),
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado B",
                    "origen": "Jalisco",
                    "precio_frecuente": 16.0,
                    "precio_minimo": 16.0,
                    "precio_maximo": 16.0,
                },
            ]
        )
        spreads = pd.DataFrame(
            {
                "fecha": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-12"]),
                "cultivo_canonico": ["aguacate", "aguacate", "aguacate"],
                "precio_mayoreo": [15.0, 15.0, 15.0],
                "precio_walmart": [30.0, 36.0, 21.0],
                "precio_chedraui": [27.0, 33.0, None],
            }
        )
        for source in ("walmart", "chedraui"):
            spreads[f"spread_{source}"] = (
                spreads[f"precio_{source}"] / spreads["precio_mayoreo"] - 1
            )

        weekly = build_weekly_price_comparison(wholesale, spreads)
        self.assertEqual(len(weekly), 2)

        first_week = weekly.iloc[0]
        self.assertEqual(first_week["semana_inicio"], pd.Timestamp("2026-01-05"))
        self.assertAlmostEqual(float(first_week["precio_mercados_mediana"]), 15.0)
        self.assertAlmostEqual(float(first_week["precio_mercados_min"]), 11.0)
        self.assertAlmostEqual(float(first_week["precio_mercados_max"]), 19.0)
        self.assertEqual(int(first_week["mercados_cubiertos"]), 2)
        self.assertAlmostEqual(float(first_week["precio_walmart"]), 33.0)
        self.assertAlmostEqual(float(first_week["precio_chedraui"]), 30.0)

        second_week = weekly.iloc[1]
        self.assertAlmostEqual(float(second_week["cambio_semanal_mercados_pct"]), 0.0)
        self.assertAlmostEqual(float(second_week["cambio_semanal_walmart_pct"]), (21.0 / 33.0) - 1)
        self.assertAlmostEqual(float(second_week["spread_walmart_vs_mercados_pct"]), 0.4)
        self.assertFalse(bool(second_week["disponible_chedraui"]))

    def test_write_price_report_embeds_selector_payload_and_missing_values(self) -> None:
        alerts = pd.DataFrame(
            [
                {
                    "cultivo_canonico": "aguacate",
                    "mercado": "Mercado A",
                    "precio_actual": 15.0,
                    "precio_pronosticado": 18.5,
                    "probabilidad_alza_10": 0.72,
                    "metodo_pronostico": "xgboost",
                    "accion_sugerida": "Adelantar compras y diversificar origen.",
                    "horizonte_dias": 28,
                    "nivel_alerta": "alto",
                }
            ]
        )
        anomalies = pd.DataFrame(
            [{"puntaje_anomalia": 3.4, "spread_retail_mayoreo": 0.55}]
        )
        weekly = pd.DataFrame(
            [
                {
                    "semana_inicio": pd.Timestamp("2026-01-05"),
                    "cultivo_canonico": "aguacate",
                    "precio_mercados_mediana": 15.0,
                    "precio_mercados_min": 11.0,
                    "precio_mercados_max": 19.0,
                    "mercados_cubiertos": 2,
                    "precio_walmart": 33.0,
                    "precio_chedraui": 30.0,
                    "dias_observados": 2,
                    "cambio_semanal_mercados_pct": None,
                    "cambio_semanal_walmart_pct": None,
                    "cambio_semanal_chedraui_pct": None,
                    "spread_walmart_vs_mercados_pct": 1.2,
                    "spread_chedraui_vs_mercados_pct": 1.0,
                    "disponible_walmart": True,
                    "disponible_chedraui": True,
                    "disponible_mercados": True,
                },
                {
                    "semana_inicio": pd.Timestamp("2026-01-12"),
                    "cultivo_canonico": "aguacate",
                    "precio_mercados_mediana": 15.0,
                    "precio_mercados_min": 14.0,
                    "precio_mercados_max": 16.0,
                    "mercados_cubiertos": 2,
                    "precio_walmart": 21.0,
                    "precio_chedraui": None,
                    "dias_observados": 1,
                    "cambio_semanal_mercados_pct": 0.0,
                    "cambio_semanal_walmart_pct": (21.0 / 33.0) - 1,
                    "cambio_semanal_chedraui_pct": None,
                    "spread_walmart_vs_mercados_pct": 0.4,
                    "spread_chedraui_vs_mercados_pct": None,
                    "disponible_walmart": True,
                    "disponible_chedraui": False,
                    "disponible_mercados": True,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            output_path = output_dir / "reporte_alertas_precios.html"
            write_price_report(alerts, anomalies, weekly, output_dir, output_path)
            html_text = output_path.read_text(encoding="utf-8")

        self.assertIn("Comparativo semanal por cultivo", html_text)
        self.assertIn('id="crop-select"', html_text)
        self.assertIn("weekly-comparison-data", html_text)
        self.assertIn("filterTablesByCrop", html_text)
        self.assertIn('data-crop="aguacate"', html_text)
        self.assertIn("s/d", html_text)
        self.assertNotIn("<th>Accion</th>", html_text)

    def test_pipeline_writes_weekly_csv_and_workbook_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            daily_root = root / "daily_runs" / "2026-01-05"
            daily_root.mkdir(parents=True)
            output_dir = root / "analysis" / "price_shock"

            sniim = pd.DataFrame(
                [
                    {
                        "fecha": "05/01/2026",
                        "producto_canonico": "aguacate",
                        "destino": "Mercado A",
                        "origen": "Michoacan",
                        "precio_frecuente": 10.0,
                        "precio_minimo": 10.0,
                        "precio_maximo": 10.0,
                    },
                    {
                        "fecha": "05/01/2026",
                        "producto_canonico": "aguacate",
                        "destino": "Mercado B",
                        "origen": "Jalisco",
                        "precio_frecuente": 20.0,
                        "precio_minimo": 20.0,
                        "precio_maximo": 20.0,
                    },
                ]
            )
            walmart = pd.DataFrame(
                [
                    {
                        "fecha_corrida": "2026-01-05",
                        "producto_canonico": "aguacate",
                        "precio_estimado_por_kg_mxn": 30.0,
                    }
                ]
            )
            chedraui = pd.DataFrame(
                [
                    {
                        "fecha_corrida": "2026-01-05",
                        "producto_canonico": "aguacate",
                        "precio_estimado_por_kg_mxn": 27.0,
                    }
                ]
            )
            with pd.ExcelWriter(daily_root / "sniim_2026-01-05.xlsx", engine="openpyxl") as writer:
                sniim.to_excel(writer, sheet_name="datos", index=False)
            with pd.ExcelWriter(daily_root / "walmart_2026-01-05.xlsx", engine="openpyxl") as writer:
                walmart.to_excel(writer, sheet_name="datos", index=False)
            with pd.ExcelWriter(daily_root / "chedraui_2026-01-05.xlsx", engine="openpyxl") as writer:
                chedraui.to_excel(writer, sheet_name="datos", index=False)

            fake_alerts = pd.DataFrame(
                [
                    {
                        "cultivo_canonico": "aguacate",
                        "mercado": "Mercado A",
                        "precio_actual": 15.0,
                        "precio_pronosticado": 16.5,
                        "probabilidad_alza_10": 0.64,
                        "metodo_pronostico": "autorregresivo",
                        "accion_sugerida": "Solicitar cotizaciones alternas y monitorear diariamente.",
                        "horizonte_dias": 28,
                        "nivel_alerta": "alto",
                    }
                ]
            )
            fake_metrics = {"horizonte_28_dias": {"metodo_operativo": "autorregresivo"}}
            fake_importance = pd.DataFrame(
                [{"feature": "precio_actual", "importance": 0.8, "horizonte_dias": 28}]
            )

            with patch(
                "src.analysis.price_shock.train_price_models",
                return_value=(fake_alerts, fake_metrics, fake_importance),
            ):
                result = run_price_shock_pipeline(daily_root.parent, output_dir, horizons=(28,))

            self.assertIn("filas_comparativo_semanal", result)
            self.assertTrue((output_dir / "comparativo_precios_semanales.csv").exists())
            self.assertTrue((output_dir / "reporte_alertas_precios.html").exists())

            with pd.ExcelFile(output_dir / "alerta_temprana_precios.xlsx") as workbook:
                self.assertIn("comparativo_semanal", workbook.sheet_names)


if __name__ == "__main__":
    unittest.main()
