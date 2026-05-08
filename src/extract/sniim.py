"""Extractor SNIIM (frutas y hortalizas) vía formulario ASP.NET real."""

from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Iterable

import openpyxl  # noqa: F401
import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.extract.spreadsheet_localization import SNIIM_EXPORT_COLUMN_MAP, rename_columns

CONSULTA_URL = (
    "https://www.economia-sniim.gob.mx/Nuevo/Consultas/MercadosNacionales/"
    "PreciosDeMercado/Agricolas/ConsultaFrutasYHortalizas.aspx?SubOpcion=4"
)
RESULTS_URL_FRAGMENTS = (
    "ResultadosConsultaFechaFrutasYHortalizas.aspx",
    "ResultadosConsultaFechasFrutasYHortalizas.aspx",
)
RESULTS_TABLE_ID = "tblResultados"
DEFAULT_OUTPUT_DIR = Path("data/raw/sniim")
HEADER_ALIASES = {
    "presentaci_n": "presentacion",
    "precio_min": "precio_minimo",
    "precio_m_n": "precio_minimo",
    "precio_m_nimo": "precio_minimo",
    "precio_max": "precio_maximo",
    "precio_frec": "precio_frecuente",
    "observaciones": "obs",
}
RESULT_TABLE_TERMS = {
    "fecha",
    "producto",
    "presentacion",
    "origen",
    "destino",
    "precio_minimo",
    "precio_maximo",
    "precio_frecuente",
    "obs",
}
PRICE_COLUMN_TERMS = {"precio_minimo", "precio_maximo", "precio_frecuente"}
CATEGORY_MARKERS = {"frutas", "hortalizas"}

LOGGER = logging.getLogger(__name__)


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _format_query_date(date_str: str) -> str:
    """Acepta YYYY-MM-DD y convierte a DD/MM/YYYY."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida '{date_str}'. Usa formato YYYY-MM-DD."
        ) from exc
    return parsed.strftime("%d/%m/%Y")


def normalize_column_name(name: str) -> str:
    replacements = {
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
        "Ã¡": "a",
        "Ã©": "e",
        "Ã­": "i",
        "Ã³": "o",
        "Ãº": "u",
        "Ã¼": "u",
        "Ã±": "n",
        "Ã": "a",
        "Ã‰": "e",
        "Ã": "i",
        "Ã“": "o",
        "Ãš": "u",
        "Ãœ": "u",
        "Ã‘": "n",
    }
    normalized = str(name).strip().replace("\xa0", " ")
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    normalized = normalized or "columna"
    return HEADER_ALIASES.get(normalized, normalized)


def clean_numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series

    cleaned = (
        series.astype(str)
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "nan": pd.NA, "None": pd.NA})
    )
    candidate = cleaned.str.replace(r"\s+", "", regex=True)
    candidate = candidate.str.replace(",", "", regex=False)
    numeric = pd.to_numeric(candidate, errors="coerce")

    if (numeric.notna().mean() if len(numeric) else 0) >= 0.6:
        return numeric
    return series


def _replace_blank_strings_with_na(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(
        lambda col: col.map(lambda value: pd.NA if isinstance(value, str) and not value.strip() else value)
    )


def _extract_form_inputs(html: str) -> dict[str, str]:
    """Extrae todos los inputs del form ASP.NET (incluyendo hidden)."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if form is None:
        raise ValueError("No se encontró el formulario ASP.NET en la página de consulta")

    payload: dict[str, str] = {}
    for tag in form.find_all("input"):
        name = tag.get("name")
        if not name:
            continue
        payload[name] = tag.get("value", "")

    # Garantizar campos ASP.NET críticos aunque vengan vacíos/ausentes.
    payload.setdefault("__VIEWSTATE", "")
    payload.setdefault("__EVENTVALIDATION", "")
    payload.setdefault("__VIEWSTATEGENERATOR", "")
    payload.setdefault("__EVENTTARGET", "")
    payload.setdefault("__EVENTARGUMENT", "")
    payload.setdefault("__LASTFOCUS", "")
    payload.setdefault("SubOpcion", "4")

    return payload


def _build_search_payload(
    base_payload: dict[str, str],
    *,
    fecha_inicio: str,
    fecha_final: str,
    producto_id: int,
    origen_id: int,
    destino_id: int,
    precios_por_id: int,
) -> dict[str, str]:
    """Preserva hidden inputs y sobreescribe campos de búsqueda reales."""
    payload = dict(base_payload)

    payload.update(
        {
            "SubOpcion": "4",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "ddlProducto": str(producto_id),
            "ddlOrigen": str(origen_id),
            "ddlDestino": str(destino_id),
            "txtFechaInicio": fecha_inicio,
            "txtFechaFinal": fecha_final,
            "ddlPrecios": str(precios_por_id),
            "btnBuscar.x": "22",
            "btnBuscar.y": "11",
        }
    )
    return payload


def _looks_like_default_columns(columns: pd.Index) -> bool:
    normalized = [normalize_column_name(c) for c in columns]
    return all(re.fullmatch(r"\d+", col) for col in normalized)


def _promote_first_row_to_header(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    promoted = df.copy()
    first_row = promoted.iloc[0].astype(str).tolist()
    promoted = promoted.iloc[1:].copy()
    promoted.columns = first_row
    promoted = promoted.reset_index(drop=True)
    return promoted


def _drop_category_marker_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    keep_mask: list[bool] = []
    for _, row in df.iterrows():
        values = []
        for value in row.tolist():
            if pd.isna(value):
                continue
            text = str(value).strip()
            if not text or text.lower() == "nan":
                continue
            values.append(normalize_column_name(text))

        unique_values = set(values)
        is_category_marker = bool(unique_values) and len(unique_values) == 1 and unique_values.issubset(
            CATEGORY_MARKERS
        )
        keep_mask.append(not is_category_marker)

    return df.loc[keep_mask].reset_index(drop=True)


def _prepare_result_table(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df
    if _looks_like_default_columns(prepared.columns) and not prepared.empty:
        prepared = _promote_first_row_to_header(prepared)
    return _drop_category_marker_rows(prepared)


def _score_result_table(df: pd.DataFrame) -> tuple[int, int]:
    normalized_cols = {normalize_column_name(c) for c in df.columns}
    col_score = len(RESULT_TABLE_TERMS.intersection(normalized_cols))

    # Algunas tablas de SNIIM vienen sin header real (columnas 0..n).
    # En ese caso intentamos usar la primera fila como encabezado.
    row_header_score = 0
    if _looks_like_default_columns(df.columns) and not df.empty:
        candidate_cols = {normalize_column_name(v) for v in df.iloc[0].astype(str).tolist()}
        row_header_score = len(RESULT_TABLE_TERMS.intersection(candidate_cols))

    best_score = max(col_score, row_header_score)
    cleaned = _replace_blank_strings_with_na(df)
    useful_rows = int(cleaned.dropna(how="all").shape[0])
    return (best_score, useful_rows)


def _select_result_table_or_raise(tables: list[pd.DataFrame]) -> pd.DataFrame:
    if not tables:
        raise ValueError("No se encontró tabla de resultados en SNIIM")

    for idx, table in enumerate(tables):
        LOGGER.info(
            "Tabla parseada #%s shape=%s columnas=%s",
            idx,
            table.shape,
            [normalize_column_name(c) for c in table.columns],
        )

    prepared_tables = [_prepare_result_table(table) for table in tables]
    scored = sorted(
        ((table, _score_result_table(table)) for table in prepared_tables),
        key=lambda x: x[1],
        reverse=True,
    )
    best_table, (best_score, _best_rows) = scored[0]

    # Match fuerte: al menos 3 términos y uno de precios.
    normalized_cols = {normalize_column_name(c) for c in best_table.columns}
    has_price_col = any(c in normalized_cols for c in PRICE_COLUMN_TERMS)
    if best_score < 3 or not has_price_col:
        raise ValueError("No se encontró una tabla de resultados confiable en SNIIM")

    return best_table


def _read_html_tables(html: str) -> list[pd.DataFrame]:
    try:
        return pd.read_html(StringIO(html))
    except ValueError:
        return []


def _parse_results_table_or_raise(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    preferred_table = soup.find("table", id=RESULTS_TABLE_ID)
    if preferred_table is not None:
        preferred_tables = _read_html_tables(str(preferred_table))
        if preferred_tables:
            return _select_result_table_or_raise(preferred_tables)

    tables = _read_html_tables(html)

    if not tables:
        tables = []
        for table_tag in soup.find_all("table"):
            try:
                tables.extend(pd.read_html(StringIO(str(table_tag))))
            except ValueError:
                continue

    return _select_result_table_or_raise(tables)


def _extract_site_product_name(html: str) -> str | None:
    product_row_match = re.search(
        r"Producto</td>.*?Calidad</td>.*?<td[^>]*class=\"DatTAB2\"[^>]*>\s*&nbsp;&nbsp;(.*?)</td>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if product_row_match:
        product_name = BeautifulSoup(product_row_match.group(1), "html.parser").get_text(" ", strip=True)
        if product_name:
            return product_name

    soup = BeautifulSoup(html, "html.parser")
    for header_cell in soup.find_all(["td", "th"]):
        if normalize_column_name(header_cell.get_text(" ", strip=True)) != "producto":
            continue

        row = header_cell.find_parent("tr")
        if row is None:
            continue

        next_row = row.find_next("tr")
        if next_row is None or next_row is row:
            continue

        data_cells = [
            cell.get_text(" ", strip=True)
            for cell in next_row.find_all(["td", "th"])
            if cell.get_text(" ", strip=True)
        ]
        if data_cells:
            return data_cells[0]

    return None


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = _drop_category_marker_rows(df.copy())
    result.columns = [normalize_column_name(c) for c in result.columns]
    result = _replace_blank_strings_with_na(result)
    result = result.dropna(how="all")
    result = result.drop_duplicates().reset_index(drop=True)

    numeric_tokens = ("precio", "min", "max", "promedio", "frecuente", "volumen", "cantidad")
    for col in result.columns:
        if any(token in col for token in numeric_tokens):
            result[col] = clean_numeric_series(result[col])

    return result


def _append_metadata(
    df: pd.DataFrame,
    *,
    fecha_inicio: str,
    fecha_final: str,
    producto_id: int,
    producto_nombre_sitio: str | None,
    origen_id: int,
    destino_id: int,
    precios_por_id: int,
) -> pd.DataFrame:
    result = df.copy()
    result["fecha_inicio_query"] = fecha_inicio
    result["fecha_final_query"] = fecha_final
    result["producto_id"] = producto_id
    result["producto_nombre_sitio"] = producto_nombre_sitio
    result["origen_id"] = origen_id
    result["destino_id"] = destino_id
    if "origen" in result.columns:
        result["origen_query"] = str(origen_id)
    else:
        result["origen"] = str(origen_id)
    if "destino" in result.columns:
        result["destino_query"] = str(destino_id)
    else:
        result["destino"] = str(destino_id)
    result["precios_por_id"] = precios_por_id
    result["registros_por_pagina"] = pd.NA
    result["fuente"] = "sniim_frutas_hortalizas"
    result["fecha_extraccion"] = datetime.now().isoformat(timespec="seconds")
    return result


def fetch_sniim_fruits_vegetables(
    fecha_inicio: str,
    fecha_final: str,
    producto_id: int,
    origen_id: int = -1,
    destino_id: int = -1,
    precios_por_id: int = 1,
    timeout: int = 60,
) -> pd.DataFrame:
    """Ejecuta búsqueda real ASP.NET y devuelve DataFrame de resultados."""
    _configure_logging()
    fecha_inicio_form = _format_query_date(fecha_inicio)
    fecha_final_form = _format_query_date(fecha_final)

    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    try:
        initial = session.get(CONSULTA_URL, timeout=timeout, headers=headers)
        initial.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise TimeoutError(f"Timeout en GET inicial a SNIIM tras {timeout} segundos") from exc
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"Error en GET inicial a SNIIM: {exc}") from exc

    base_payload = _extract_form_inputs(initial.text)
    payload = _build_search_payload(
        base_payload,
        fecha_inicio=fecha_inicio_form,
        fecha_final=fecha_final_form,
        producto_id=producto_id,
        origen_id=origen_id,
        destino_id=destino_id,
        precios_por_id=precios_por_id,
    )

    try:
        response = session.post(
            CONSULTA_URL,
            data=payload,
            timeout=timeout,
            allow_redirects=True,
            headers=headers,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise TimeoutError(f"Timeout en POST de búsqueda SNIIM tras {timeout} segundos") from exc
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"Error en POST de búsqueda SNIIM: {exc}") from exc

    LOGGER.info("Final URL after POST: %s", response.url)

    if not any(fragment in response.url for fragment in RESULTS_URL_FRAGMENTS):
        raise ValueError("No se llegó a la página real de resultados de SNIIM")

    try:
        parsed = _parse_results_table_or_raise(response.text)
    except Exception as exc:
        preview = (response.text or "")[:500]
        LOGGER.error("Parsing failed. status=%s url=%s", response.status_code, response.url)
        print(preview)
        raise ValueError(
            "No se pudo parsear la tabla de resultados de SNIIM. "
            f"status_code={response.status_code}, url={response.url}, body_preview={preview!r}"
        ) from exc

    producto_nombre_sitio = _extract_site_product_name(response.text)
    cleaned = _normalize_dataframe(parsed)
    if cleaned.empty:
        preview = (response.text or "")[:500]
        print(preview)
        raise ValueError(
            "La tabla de resultados quedó vacía tras limpieza. "
            f"status_code={response.status_code}, url={response.url}, body_preview={preview!r}"
        )

    return _append_metadata(
        cleaned,
        fecha_inicio=fecha_inicio,
        fecha_final=fecha_final,
        producto_id=producto_id,
        producto_nombre_sitio=producto_nombre_sitio,
        origen_id=origen_id,
        destino_id=destino_id,
        precios_por_id=precios_por_id,
    )


def _resolve_output_path(output_dir: str, base_name: str, output_format: str) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_base = re.sub(r"[^a-zA-Z0-9_.-]+", "_", base_name).strip("_")
    return output_path / f"{safe_base}.{output_format}"


def _write_html_xls(df: pd.DataFrame, output_path: Path) -> None:
    html = df.to_html(index=False, na_rep="", border=1)
    output_path.write_text(html, encoding="utf-8")


def save_sniim_output(df: pd.DataFrame, output_dir: str, base_name: str, output_format: str) -> Path:
    output_path = _resolve_output_path(output_dir, base_name, output_format)
    localized_df = rename_columns(df, SNIIM_EXPORT_COLUMN_MAP)

    if output_format == "csv":
        localized_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    elif output_format == "xlsx":
        localized_df.to_excel(output_path, index=False, engine="openpyxl")
    elif output_format == "xls":
        _write_html_xls(localized_df, output_path)
    else:
        raise ValueError(f"Formato de salida no soportado: {output_format}")

    return output_path


def _build_base_name(producto_id: int, fecha_inicio: str, fecha_final: str) -> str:
    return f"sniim_producto_{producto_id}_{fecha_inicio}_{fecha_final}"


def _parse_cli_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extractor SNIIM frutas y hortalizas")
    parser.add_argument("--fecha-inicio", required=True, help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--fecha-final", required=True, help="Fecha final YYYY-MM-DD")
    parser.add_argument("--producto-id", required=True, type=int, help="ID de producto")
    parser.add_argument("--origen-id", type=int, default=-1)
    parser.add_argument("--destino-id", type=int, default=-1)
    parser.add_argument("--precios-por-id", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--output-format",
        choices=("csv", "xls", "xlsx"),
        default="xlsx",
        help="Formato de salida. Por defecto: xlsx",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_cli_args(argv)
    df = fetch_sniim_fruits_vegetables(
        fecha_inicio=args.fecha_inicio,
        fecha_final=args.fecha_final,
        producto_id=args.producto_id,
        origen_id=args.origen_id,
        destino_id=args.destino_id,
        precios_por_id=args.precios_por_id,
        timeout=args.timeout,
    )

    print(f"DataFrame shape: {df.shape}")
    base_name = _build_base_name(args.producto_id, args.fecha_inicio, args.fecha_final)
    output_path = save_sniim_output(df, args.output_dir, base_name, args.output_format)
    print(f"{args.output_format.upper()}: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
