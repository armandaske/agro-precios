from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analysis.common import normalize_product, write_parquet_with_metadata
from src.extract.fred_public_csv import normalize_fred_dexmxus
from src.extract.imf_commodities import normalize_imf_commodity_file
from src.extract.usda_specialty_crops_files import normalize_usda_specialty_crop_file
from src.extract.world_bank_commodities import normalize_world_bank_prices

PROXY_SHEET_NAME = "proxies_internacionales"
PROXY_COLUMNS = [
    "activo",
    "producto_canonico",
    "proxy_id",
    "fuente",
    "serie",
    "tipo_proxy",
    "uso_modelo",
    "frecuencia",
    "moneda",
    "unidad_origen",
    "nota_metodologica",
]

DEFAULT_PROXY_ROWS = [
    *[
        {
            "activo": True,
            "producto_canonico": product,
            "proxy_id": f"usda_ams_{slug}",
            "fuente": "usda_ams",
            "serie": keyword,
            "tipo_proxy": strength,
            "uso_modelo": "feature",
            "frecuencia": "diaria",
            "moneda": "USD",
            "unidad_origen": "segun_reporte_usda",
            "nota_metodologica": "Precio de mercado mayorista de EE. UU. desde archivos publicos descargados de USDA AMS.",
        }
        for product, slug, keyword, strength in [
            ("Aguacate", "aguacate", "avocado", "fuerte"),
            ("Tomate rojo", "tomate_rojo", "tomato", "fuerte"),
            ("Limón", "limon", "lime", "fuerte"),
            ("Mango", "mango", "mango", "fuerte"),
            ("Chile verde", "chile_verde", "pepper", "medio"),
            ("Cebolla", "cebolla", "onion", "medio"),
            ("Papa", "papa", "potato", "medio"),
            ("Zanahoria", "zanahoria", "carrot", "medio"),
        ]
    ],
    *[
        {
            "activo": True,
            "producto_canonico": product,
            "proxy_id": "fx_usdmxn",
            "fuente": "fred",
            "serie": "DEXMXUS",
            "tipo_proxy": "fx",
            "uso_modelo": "feature",
            "frecuencia": "diaria",
            "moneda": "MXN",
            "unidad_origen": "MXN por USD",
            "nota_metodologica": "Tipo de cambio spot MXN por USD publicado en FRED; no requiere token.",
        }
        for product in [
            "Aguacate",
            "Tomate rojo",
            "Limón",
            "Mango",
            "Chile verde",
            "Cebolla",
            "Papa",
            "Zanahoria",
            "Plátano",
            "Elote",
        ]
    ],
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
        "nota_metodologica": "Proxy macro de maiz; no equivale directamente a elote fresco.",
    },
    {
        "activo": True,
        "producto_canonico": "Plátano",
        "proxy_id": "world_bank_banana_us",
        "fuente": "world_bank",
        "serie": "Banana, US",
        "tipo_proxy": "medio",
        "uso_modelo": "diagnostico_only",
        "frecuencia": "mensual",
        "moneda": "USD",
        "unidad_origen": "$/kg",
        "nota_metodologica": "Precio internacional de banana como contexto; validar antes de usar operacionalmente.",
    },
    {
        "activo": True,
        "producto_canonico": "Limón",
        "proxy_id": "world_bank_orange",
        "fuente": "world_bank",
        "serie": "Orange",
        "tipo_proxy": "debil",
        "uso_modelo": "diagnostico_only",
        "frecuencia": "mensual",
        "moneda": "USD",
        "unidad_origen": "$/kg",
        "nota_metodologica": "Proxy citrico debil; mantener como diagnostico salvo evidencia de backtesting.",
    },
]


def default_proxy_config() -> pd.DataFrame:
    return pd.DataFrame(DEFAULT_PROXY_ROWS, columns=PROXY_COLUMNS)


def load_proxy_config(config_path: Path) -> pd.DataFrame:
    if not config_path.exists():
        return default_proxy_config()
    with pd.ExcelFile(config_path) as workbook:
        sheet_map = {str(name).casefold(): name for name in workbook.sheet_names}
        sheet_name = sheet_map.get(PROXY_SHEET_NAME.casefold())
        if not sheet_name:
            return default_proxy_config()
        config = pd.read_excel(config_path, sheet_name=sheet_name)
    for column in PROXY_COLUMNS:
        if column not in config.columns:
            config[column] = pd.NA
    config = config[PROXY_COLUMNS].dropna(how="all")
    return config if not config.empty else default_proxy_config()


def load_public_price_records(raw_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted((raw_root / "world_bank").glob("*.xls*")):
        frames.append(normalize_world_bank_prices(path))
    for path in sorted((raw_root / "fred").glob("*.csv")):
        frames.append(normalize_fred_dexmxus(path))
    for path in sorted((raw_root / "imf").glob("*")):
        if path.suffix.lower() in {".csv", ".xlsx", ".xls"}:
            frames.append(normalize_imf_commodity_file(path))
    for path in sorted((raw_root / "usda_ams").glob("*")):
        if path.suffix.lower() in {".csv", ".xlsx", ".xls"}:
            frames.append(normalize_usda_specialty_crop_file(path))
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return _empty_price_records()
    records = pd.concat(frames, ignore_index=True, sort=False)
    records["fecha"] = pd.to_datetime(records["fecha"], errors="coerce")
    records["precio_original"] = pd.to_numeric(records["precio_original"], errors="coerce")
    return records.dropna(subset=["fecha", "serie", "precio_original"]).reset_index(drop=True)


def build_international_price_features(
    config_path: Path,
    raw_root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    proxy_config = load_proxy_config(config_path)
    active = proxy_config[proxy_config["activo"].map(_parse_bool)].copy()
    if active.empty:
        return _empty_features(), proxy_config

    records = load_public_price_records(raw_root)
    if records.empty:
        return _empty_features(), proxy_config

    fx = _fx_records(records)
    rows: list[pd.DataFrame] = []
    for proxy in active.to_dict(orient="records"):
        matched = _match_records(records, proxy)
        if matched.empty:
            continue
        enriched = matched.copy()
        for column in (
            "producto_canonico",
            "proxy_id",
            "tipo_proxy",
            "uso_modelo",
            "nota_metodologica",
        ):
            enriched[column] = proxy.get(column)
        enriched["producto_canonico"] = enriched["producto_canonico"].map(normalize_product)
        enriched["precio_usd"] = pd.NA
        enriched["precio_mxn"] = pd.NA

        if str(proxy.get("fuente", "")).casefold() == "fred":
            enriched["tipo_cambio_mxn_usd"] = pd.NA
            enriched["precio_mxn"] = enriched["precio_original"]
            enriched["valor_modelo"] = enriched["precio_original"]
        else:
            enriched["precio_usd"] = enriched["precio_original"]
            enriched = _attach_fx(enriched, fx)
            enriched["precio_mxn"] = enriched["precio_usd"] * enriched["tipo_cambio_mxn_usd"]
            enriched["valor_modelo"] = enriched["precio_mxn"].where(
                enriched["precio_mxn"].notna(),
                enriched["precio_usd"],
            )
        rows.append(enriched)

    if not rows:
        return _empty_features(), proxy_config
    features = pd.concat(rows, ignore_index=True, sort=False)
    features["fecha_disponible"] = features.apply(_available_date, axis=1)
    features = _add_proxy_diagnostics(features)
    return features.reindex(columns=_feature_columns()).sort_values(
        ["producto_canonico", "proxy_id", "fecha"]
    ).reset_index(drop=True), proxy_config


def write_international_price_features(
    config_path: Path,
    raw_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    features, proxy_config = build_international_price_features(config_path, raw_root)
    generated_at = datetime.now().isoformat(timespec="seconds")
    write_parquet_with_metadata(
        features,
        output_path,
        metadata={
            "generado_en": generated_at,
            "configuracion": str(config_path),
            "raiz_fuentes_publicas": str(raw_root),
            "filas": len(features),
            "proxies_configurados": len(proxy_config),
            "proxies_con_datos": int(features["proxy_id"].nunique()) if not features.empty else 0,
            "sin_tokens_api": True,
        },
    )
    return {
        "output_path": str(output_path),
        "filas": len(features),
        "proxies_configurados": len(proxy_config),
        "proxies_con_datos": int(features["proxy_id"].nunique()) if not features.empty else 0,
    }


def _match_records(records: pd.DataFrame, proxy: dict[str, Any]) -> pd.DataFrame:
    source = str(proxy.get("fuente", "")).casefold().strip()
    series = str(proxy.get("serie", "")).casefold().strip()
    subset = records[records["fuente"].astype(str).str.casefold().eq(source)].copy()
    if subset.empty or not series:
        return subset.iloc[0:0]
    if source == "usda_ams":
        normalized_series = subset["serie"].astype(str).str.casefold()
        return subset[normalized_series.str.contains(series, regex=False, na=False)].copy()
    return subset[subset["serie"].astype(str).str.casefold().eq(series)].copy()


def _fx_records(records: pd.DataFrame) -> pd.DataFrame:
    fx = records[
        records["fuente"].astype(str).str.casefold().eq("fred")
        & records["serie"].astype(str).str.casefold().eq("dexmxus")
    ][["fecha", "precio_original"]].copy()
    return fx.rename(columns={"precio_original": "tipo_cambio_mxn_usd"}).sort_values("fecha")


def _attach_fx(frame: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    frame = frame.drop(columns=["tipo_cambio_mxn_usd"], errors="ignore")
    if fx.empty:
        frame["tipo_cambio_mxn_usd"] = pd.NA
        return frame
    merged = pd.merge_asof(
        frame.sort_values("fecha"),
        fx,
        on="fecha",
        direction="backward",
    )
    return merged


def _available_date(row: pd.Series) -> pd.Timestamp:
    date_value = pd.Timestamp(row["fecha"])
    frequency = str(row.get("frecuencia", "")).casefold()
    if frequency.startswith("mens"):
        return date_value + pd.offsets.MonthEnd(0) + pd.Timedelta(days=7)
    return date_value


def _add_proxy_diagnostics(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    result = result.sort_values(["producto_canonico", "proxy_id", "fecha"])
    group = result.groupby(["producto_canonico", "proxy_id"], sort=False)["valor_modelo"]
    result["cambio_1_periodo"] = group.pct_change(1)
    result["cambio_3_periodos"] = group.pct_change(3)
    rolling_mean = group.transform(lambda values: values.shift(1).rolling(12, min_periods=4).mean())
    rolling_std = group.transform(lambda values: values.shift(1).rolling(12, min_periods=4).std())
    result["zscore_12_periodos"] = (result["valor_modelo"] - rolling_mean) / rolling_std.replace(0, pd.NA)
    return result


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().casefold() in {"1", "true", "t", "yes", "y", "si", "s", "x"}


def _feature_columns() -> list[str]:
    return [
        "fecha",
        "fecha_disponible",
        "producto_canonico",
        "proxy_id",
        "fuente",
        "serie",
        "precio_original",
        "precio_usd",
        "precio_mxn",
        "valor_modelo",
        "tipo_cambio_mxn_usd",
        "frecuencia",
        "tipo_proxy",
        "uso_modelo",
        "moneda",
        "unidad_origen",
        "cambio_1_periodo",
        "cambio_3_periodos",
        "zscore_12_periodos",
        "nota_metodologica",
        "archivo_fuente",
    ]


def _empty_price_records() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "fecha",
            "serie",
            "precio_original",
            "moneda",
            "unidad_origen",
            "frecuencia",
            "fuente",
            "archivo_fuente",
        ]
    )


def _empty_features() -> pd.DataFrame:
    return pd.DataFrame(columns=_feature_columns())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construye features de precios internacionales publicos.")
    parser.add_argument("--config", type=Path, default=Path("config/products.xlsx"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/international_prices"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/analysis/international_prices/international_price_features.parquet"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = write_international_price_features(args.config, args.raw_root, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
