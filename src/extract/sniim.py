"""Extractor de precios SNIIM para frutas y hortalizas.

Este módulo consulta la URL pública de resultados de SNIIM usando parámetros
por query string, parsea la tabla HTML y devuelve un DataFrame limpio.
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

import openpyxl  # noqa: F401  # requerido como motor para exportación XLSX
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_RESULTS_URL = (
    "https://www.economia-sniim.gob.mx/nuevo/Consultas/MercadosNacionales/"
    "PreciosDeMercado/Agricolas/ResultadosConsultaFechasFrutasYHortalizas.aspx"
)

DEFAULT_OUTPUT_DIR = Path("data/raw/sniim")

# Mantener este mapeo editable por si SNIIM ajusta nombres de parámetros.
QUERY_PARAM_NAMES = {
    "fecha_inicio": "fechaInicio",
    "fecha_final": "fechaFinal",
    "producto_id": "ProductoId",
    "origen_id": "OrigenId",
    "origen": "Origen",
    "destino_id": "DestinoId",
    "destino": "Destino",
    "precios_por_id": "PreciosPorId",
    "registros_por_pagina": "RegistrosPorPagina",
}

LOGGER = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configura logging básico si no existe configuración previa."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _format_query_date(date_str: str) -> str:
    """Convierte YYYY-MM-DD a DD/MM/YYYY para la query de SNIIM."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida '{date_str}'. Usa el formato YYYY-MM-DD."
        ) from exc
    return parsed.strftime("%d/%m/%Y")


def normalize_column_name(name: str) -> str:
    """Normaliza nombre de columna a snake_case sin acentos."""
    replacements = str.maketrans(
        {
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ü": "u",
            "ñ": "n",
            "Á": "a",
            "É": "e",
            "Í": "i",
            "Ó": "o",
            "Ú": "u",
            "Ü": "u",
            "Ñ": "n",
        }
    )
    normalized = str(name).strip().translate(replacements).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "columna"


def clean_numeric_series(series: pd.Series) -> pd.Series:
    """Limpia una serie textual numérica y la convierte a float cuando aplique."""
    if pd.api.types.is_numeric_dtype(series):
        return series

    cleaned = (
        series.astype(str)
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "nan": pd.NA, "None": pd.NA})
    )

    # Reglas para formatos comunes en México: 1,234.56 / 1234 / 12.5
    candidate = cleaned.str.replace(r"\s+", "", regex=True)
    candidate = candidate.str.replace(",", "", regex=False)
    numeric = pd.to_numeric(candidate, errors="coerce")

    # Solo convertimos si hay evidencia razonable de que la columna es numérica.
    ratio_numeric = numeric.notna().mean() if len(numeric) else 0
    if ratio_numeric >= 0.6:
        return numeric
    return series


def _score_table(df: pd.DataFrame) -> tuple[int, int]:
    """Asigna un puntaje heurístico para elegir la tabla más probable."""
    if df.empty:
        return (0, 0)

    col_text = " ".join(str(c).lower() for c in df.columns)
    keywords = [
        "precio",
        "producto",
        "origen",
        "destino",
        "fecha",
        "mercado",
        "min",
        "max",
        "frecuente",
    ]
    keyword_score = sum(1 for kw in keywords if kw in col_text)

    useful_rows = int(df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all").shape[0])
    return (keyword_score, useful_rows)


def _parse_with_read_html(html: str) -> pd.DataFrame:
    """Primer intento de parsing usando pandas.read_html."""
    try:
        tables = pd.read_html(html)
    except ValueError:
        tables = []

    if not tables:
        raise ValueError("No se encontró tabla de resultados en SNIIM")

    best = max(tables, key=_score_table)
    return best


def _parse_with_bs4(html: str) -> pd.DataFrame:
    """Fallback de parsing: localizar tabla con BeautifulSoup y parsear de nuevo."""
    soup = BeautifulSoup(html, "html.parser")
    html_tables = soup.find_all("table")
    if not html_tables:
        raise ValueError("No se encontró tabla de resultados en SNIIM")

    parsed_tables: list[pd.DataFrame] = []
    for table in html_tables:
        try:
            parsed_tables.extend(pd.read_html(str(table)))
        except ValueError:
            continue

    if not parsed_tables:
        raise ValueError("No se encontró tabla de resultados en SNIIM")

    return max(parsed_tables, key=_score_table)


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica limpieza de columnas, filas y tipos de datos."""
    df = df.copy()
    df.columns = [normalize_column_name(col) for col in df.columns]

    df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all")
    df = df.drop_duplicates().reset_index(drop=True)

    numeric_hint_tokens = (
        "precio",
        "min",
        "max",
        "promedio",
        "frecuente",
        "volumen",
        "cantidad",
    )

    for col in df.columns:
        if any(token in col for token in numeric_hint_tokens):
            df[col] = clean_numeric_series(df[col])

    return df


def _append_metadata(
    df: pd.DataFrame,
    *,
    fecha_inicio: str,
    fecha_final: str,
    producto_id: int,
    origen_id: int,
    origen: str,
    destino_id: int,
    destino: str,
    precios_por_id: int,
    registros_por_pagina: int,
) -> pd.DataFrame:
    """Agrega columnas de metadata de consulta y trazabilidad."""
    result = df.copy()
    result["fecha_inicio_query"] = fecha_inicio
    result["fecha_final_query"] = fecha_final
    result["producto_id"] = producto_id
    result["origen_id"] = origen_id
    result["origen"] = origen
    result["destino_id"] = destino_id
    result["destino"] = destino
    result["precios_por_id"] = precios_por_id
    result["registros_por_pagina"] = registros_por_pagina
    result["fuente"] = "sniim_frutas_hortalizas"
    result["fecha_extraccion"] = datetime.now().isoformat(timespec="seconds")
    return result


def fetch_sniim_fruits_vegetables(
    fecha_inicio: str,
    fecha_final: str,
    producto_id: int,
    origen_id: int = -1,
    origen: str = "Todos",
    destino_id: int = -1,
    destino: str = "Todos",
    precios_por_id: int = 1,
    registros_por_pagina: int = 500,
    timeout: int = 60,
) -> pd.DataFrame:
    """Consulta resultados de SNIIM y devuelve un DataFrame limpio."""
    _configure_logging()

    fecha_inicio_query = _format_query_date(fecha_inicio)
    fecha_final_query = _format_query_date(fecha_final)

    params = {
        QUERY_PARAM_NAMES["fecha_inicio"]: fecha_inicio_query,
        QUERY_PARAM_NAMES["fecha_final"]: fecha_final_query,
        QUERY_PARAM_NAMES["producto_id"]: int(producto_id),
        QUERY_PARAM_NAMES["origen_id"]: int(origen_id),
        QUERY_PARAM_NAMES["origen"]: str(origen),
        QUERY_PARAM_NAMES["destino_id"]: int(destino_id),
        QUERY_PARAM_NAMES["destino"]: str(destino),
        QUERY_PARAM_NAMES["precios_por_id"]: int(precios_por_id),
        QUERY_PARAM_NAMES["registros_por_pagina"]: int(registros_por_pagina),
    }

    LOGGER.info("Consultando SNIIM: %s?%s", BASE_RESULTS_URL, urlencode(params))

    session = requests.Session()
    try:
        response = session.get(BASE_RESULTS_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise TimeoutError(
            f"Timeout al consultar SNIIM tras {timeout} segundos"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"Error al consultar SNIIM: {exc}") from exc

    html = response.text

    try:
        parsed = _parse_with_read_html(html)
    except ValueError:
        parsed = _parse_with_bs4(html)

    if parsed.empty:
        raise ValueError("No se encontró tabla de resultados en SNIIM")

    cleaned = _normalize_dataframe(parsed)
    if cleaned.empty:
        raise ValueError("No se encontró tabla de resultados en SNIIM")

    return _append_metadata(
        cleaned,
        fecha_inicio=fecha_inicio,
        fecha_final=fecha_final,
        producto_id=producto_id,
        origen_id=origen_id,
        origen=origen,
        destino_id=destino_id,
        destino=destino,
        precios_por_id=precios_por_id,
        registros_por_pagina=registros_por_pagina,
    )


def save_sniim_output(df: pd.DataFrame, output_dir: str, base_name: str) -> dict[str, str]:
    """Guarda DataFrame en CSV y XLSX y devuelve rutas generadas."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    safe_base = re.sub(r"[^a-zA-Z0-9_.-]+", "_", base_name).strip("_")
    csv_path = output_path / f"{safe_base}.csv"
    xlsx_path = output_path / f"{safe_base}.xlsx"

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False, engine="openpyxl")

    return {
        "csv": str(csv_path),
        "xlsx": str(xlsx_path),
    }


def _build_base_name(producto_id: int, fecha_inicio: str, fecha_final: str) -> str:
    """Genera nombre base de salida."""
    return f"sniim_producto_{producto_id}_{fecha_inicio}_{fecha_final}"


def _parse_cli_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    """Define argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(description="Extractor SNIIM frutas y hortalizas")
    parser.add_argument("--fecha-inicio", required=True, help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--fecha-final", required=True, help="Fecha final YYYY-MM-DD")
    parser.add_argument("--producto-id", required=True, type=int, help="ID de producto")
    parser.add_argument("--origen-id", type=int, default=-1)
    parser.add_argument("--origen", default="Todos")
    parser.add_argument("--destino-id", type=int, default=-1)
    parser.add_argument("--destino", default="Todos")
    parser.add_argument("--precios-por-id", type=int, default=1)
    parser.add_argument("--registros-por-pagina", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    """Entry point CLI."""
    args = _parse_cli_args(argv)

    df = fetch_sniim_fruits_vegetables(
        fecha_inicio=args.fecha_inicio,
        fecha_final=args.fecha_final,
        producto_id=args.producto_id,
        origen_id=args.origen_id,
        origen=args.origen,
        destino_id=args.destino_id,
        destino=args.destino,
        precios_por_id=args.precios_por_id,
        registros_por_pagina=args.registros_por_pagina,
        timeout=args.timeout,
    )

    print(f"DataFrame shape: {df.shape}")

    base_name = _build_base_name(args.producto_id, args.fecha_inicio, args.fecha_final)
    outputs = save_sniim_output(df, args.output_dir, base_name)

    print(f"CSV:  {outputs['csv']}")
    print(f"XLSX: {outputs['xlsx']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
