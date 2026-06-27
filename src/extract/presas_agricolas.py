"""Extractor HTTP para el portal de Presas Agricolas.

Soporta tres tipos de consulta configurables desde Excel:
- `presas_periodo`: obtiene el corte de todas las presas para anio/mes/decena; con
  `anio_final` explicito recorre todos los cortes hasta fin de ese anio.
- `presas_estado`: obtiene el corte filtrado por estado para anio/mes/decena.
- `serie_presa`: obtiene la serie historica por presa para un mes/decena dado.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://presasagricolas.agricultura.gob.mx/"
DEFAULT_CONFIG_PATH = Path("config/presas_agricolas.xlsx")
DEFAULT_OUTPUT_DIR = Path("data/raw/presas_agricolas")
DEFAULT_TIMEOUT = 45
QUERY_SHEET_NAME = "consultas"
QUERY_SHEET_NAME_ALIASES = ("consultas", "queries")
INSTRUCTIONS_SHEET_NAME = "instrucciones"
CATALOG_SHEET_NAME = "catalogo_presas"
CATALOG_SHEET_NAME_ALIASES = ("catalogo_presas", "presas_catalogo", "catalog")
SUPPORTED_QUERY_TYPES = {"presas_periodo", "presas_estado", "serie_presa"}

LOGGER = logging.getLogger("presas_agricolas")

QUERY_COLUMN_ALIASES = {
    "activo": "active",
    "active": "active",
    "nombre_consulta": "query_name",
    "query_name": "query_name",
    "tipo_consulta": "query_type",
    "query_type": "query_type",
    "id_conagua": "id_conagua",
    "conagua_id": "id_conagua",
    "anio": "year",
    "year": "year",
    "mes": "month",
    "month": "month",
    "decena": "day_block",
    "day_block": "day_block",
    "anio_inicial": "start_year",
    "start_year": "start_year",
    "anio_final": "end_year",
    "end_year": "end_year",
    "nombre_oficial": "dam_name",
    "dam_name": "dam_name",
    "estado": "state",
    "state": "state",
}

QUERY_EXPORT_COLUMN_MAP = {
    "active": "activo",
    "query_name": "nombre_consulta",
    "query_type": "tipo_consulta",
    "id_conagua": "id_conagua",
    "year": "anio",
    "month": "mes",
    "day_block": "decena",
    "start_year": "anio_inicial",
    "end_year": "anio_final",
    "dam_name": "nombre_oficial",
    "state": "estado",
}

INSTRUCTIONS_EXPORT_COLUMN_MAP = {
    "campo": "campo",
    "descripcion": "descripcion",
}

CATALOG_EXPORT_COLUMN_MAP = {
    "id_conagua": "id_conagua",
    "nombre_oficial": "nombre_oficial",
    "nombre_comun": "nombre_comun",
    "estado": "estado",
    "municipio": "municipio",
    "uso_principal": "uso_principal",
    "distrito_riego": "distrito_riego",
    "latitud": "latitud",
    "longitud": "longitud",
    "detalle_presa_url": "detalle_presa_url",
    "anio": "anio_catalogo",
    "mes": "mes_catalogo",
    "decena": "decena_catalogo",
    "periods_seen_count": "periodos_observados",
    "first_seen_year": "anio_primer_avistamiento",
    "first_seen_month": "mes_primer_avistamiento",
    "first_seen_day_block": "decena_primer_avistamiento",
    "last_seen_year": "anio_ultimo_avistamiento",
    "last_seen_month": "mes_ultimo_avistamiento",
    "last_seen_day_block": "decena_ultimo_avistamiento",
}


SNAPSHOT_COLUMN_MAP = {
    "config_row_number": "numero_fila_config",
    "query_name": "nombre_consulta",
    "query_type": "tipo_consulta",
    "requested_id_conagua": "id_conagua_solicitado",
    "requested_state": "estado_solicitado",
    "query_year": "anio_consulta",
    "query_month": "mes_consulta",
    "query_day_block": "decena_consulta",
    "id_conagua": "id_conagua",
    "nombre_oficial": "nombre_oficial",
    "nombre_comun": "nombre_comun",
    "estado": "estado",
    "municipio": "municipio",
    "uso_principal": "uso_principal",
    "distrito_riego": "distrito_riego",
    "anio": "anio_dato",
    "mes": "mes_dato",
    "decena": "decena_dato",
    "porcentaje_almacenamiento": "porcentaje_almacenamiento",
    "almacenamiento_hm3": "almacenamiento_hm3",
    "capacidad_name_hm3": "capacidad_name_hm3",
    "capacidad_namo_hm3": "capacidad_namo_hm3",
    "latitud": "latitud",
    "longitud": "longitud",
    "detalle_presa_url": "detalle_presa_url",
    "fuente": "fuente",
    "fecha_extraccion": "fecha_extraccion",
}

SERIES_COLUMN_MAP = {
    "config_row_number": "numero_fila_config",
    "query_name": "nombre_consulta",
    "query_type": "tipo_consulta",
    "query_year": "anio_consulta",
    "query_month": "mes_consulta",
    "query_day_block": "decena_consulta",
    "query_start_year": "anio_inicial_consulta",
    "query_end_year": "anio_final_consulta",
    "id_conagua": "id_conagua",
    "nombre_oficial": "nombre_oficial",
    "nombre_comun": "nombre_comun",
    "estado": "estado",
    "municipio": "municipio",
    "uso_principal": "uso_principal",
    "distrito_riego": "distrito_riego",
    "anio": "anio_dato",
    "mes": "mes_dato",
    "decena": "decena_dato",
    "porcentaje_almacenamiento": "porcentaje_almacenamiento",
    "almacenamiento_hm3": "almacenamiento_hm3",
    "capacidad_name_hm3": "capacidad_name_hm3",
    "capacidad_namo_hm3": "capacidad_namo_hm3",
    "latitud": "latitud",
    "longitud": "longitud",
    "detalle_presa_url": "detalle_presa_url",
    "fuente": "fuente",
    "fecha_extraccion": "fecha_extraccion",
}

ERROR_COLUMN_MAP = {
    "config_row_number": "numero_fila_config",
    "query_name": "nombre_consulta",
    "query_type": "tipo_consulta",
    "error": "error",
}

META_COLUMN_MAP = {
    "config_path": "ruta_configuracion",
    "executed_at": "fecha_ejecucion",
    "queries_attempted": "consultas_intentadas",
    "queries_succeeded": "consultas_exitosas",
    "queries_failed": "consultas_con_error",
    "available_year_min": "anio_minimo_disponible",
    "available_year_max": "anio_maximo_disponible",
}


@dataclass
class PresaQuery:
    row_number: int
    query_name: str
    query_type: str
    id_conagua: str | None
    year: int
    month: int
    day_block: int
    start_year: int | None
    end_year: int | None
    range_end_year: int | None
    dam_name: str | None
    state: str | None


def configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "si", "s", "x"}


def _clean_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _parse_optional_int(value: Any) -> int | None:
    if pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value).strip())


def _is_explicit_value(value: Any) -> bool:
    return not pd.isna(value) and str(value).strip() != ""


def _ensure_ok_response(response: requests.Response, context: str) -> None:
    if response.status_code >= 400:
        raise RuntimeError(f"{context} fallo: HTTP {response.status_code}")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            ),
            "Referer": BASE_URL + "inicio.php",
        }
    )
    return session


def _request_json(
    session: requests.Session,
    path: str,
    *,
    method: str = "post",
    data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    url = BASE_URL + path
    if method.lower() == "get":
        response = session.get(url, params=data, timeout=DEFAULT_TIMEOUT)
    else:
        response = session.post(url, data=data or {}, timeout=DEFAULT_TIMEOUT)
    _ensure_ok_response(response, path)

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        snippet = re.sub(r"\s+", " ", response.text).strip()[:240]
        content_type = response.headers.get("Content-Type", "")
        detail = f"{path} devolvio una respuesta no-JSON"
        if content_type:
            detail += f" (content-type: {content_type})"
        if snippet:
            detail += f" | inicio_respuesta={snippet}"
        raise RuntimeError(detail) from exc

    if not isinstance(payload, list):
        raise RuntimeError(f"{path} devolvio un payload inesperado")
    return payload


def fetch_available_years(session: requests.Session | None = None) -> list[int]:
    own_session = session is None
    session = session or _session()
    try:
        payload = _request_json(session, "js/ajax/getAnios.php")
    finally:
        if own_session:
            session.close()

    years = []
    for item in payload:
        year = _parse_optional_int(item.get("anio"))
        if year is not None:
            years.append(year)
    if not years:
        raise RuntimeError("El portal no devolvio anios disponibles")
    return years


def fetch_default_period(session: requests.Session | None = None) -> dict[str, int]:
    own_session = session is None
    session = session or _session()
    try:
        payload = _request_json(session, "js/ajax/getInicio.php")
    finally:
        if own_session:
            session.close()

    if not payload:
        raise RuntimeError("El portal no devolvio periodo inicial")
    first = payload[0]
    year = _parse_optional_int(first.get("anio"))
    month = _parse_optional_int(first.get("mes"))
    day_block = _parse_optional_int(first.get("decena"))
    if year is None or month is None or day_block is None:
        raise RuntimeError("El portal devolvio un periodo inicial incompleto")
    return {"year": year, "month": month, "day_block": day_block}


def _normalize_text(value: Any) -> str:
    text = html.unescape(_clean_string(value))
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _slug_text(value: Any) -> str:
    text = _normalize_text(value)
    normalized = text
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
    normalized = normalized.translate(replacements)
    normalized = normalized.encode("ascii", "ignore").decode("ascii") if normalized else ""
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized


def _filter_snapshot_by_state(snapshot_df: pd.DataFrame, state: str | None) -> pd.DataFrame:
    if not state:
        return snapshot_df
    state_norm = _slug_text(state)
    return snapshot_df.loc[snapshot_df["estado"].map(_slug_text) == state_norm].reset_index(drop=True)


def _normalize_float(value: Any) -> float | None:
    text = _normalize_text(value)
    if not text:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_portal_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_conagua": _normalize_text(record.get("CveCONAGUAPresa")),
        "nombre_oficial": _normalize_text(record.get("nombreOficial")),
        "nombre_comun": _normalize_text(record.get("nombreComun")),
        "estado": _normalize_text(record.get("nombreEstado")),
        "municipio": _normalize_text(record.get("nombreMpio")),
        "uso_principal": _normalize_text(record.get("nombreUso")),
        "distrito_riego": _normalize_text(record.get("DRiego")),
        "anio": _parse_optional_int(record.get("anio")),
        "mes": _parse_optional_int(record.get("cveMes")),
        "decena": _parse_optional_int(record.get("cveDecena")),
        "porcentaje_almacenamiento": _normalize_float(record.get("porcAlmacen")),
        "almacenamiento_hm3": _normalize_float(record.get("Almacenamiento")),
        "capacidad_name_hm3": _normalize_float(record.get("NAME")),
        "capacidad_namo_hm3": _normalize_float(record.get("NAMO")),
        "latitud": _normalize_float(record.get("Y")),
        "longitud": _normalize_float(record.get("X")),
        "detalle_presa_url": _normalize_text(record.get("LinkPresa")),
    }


def fetch_snapshot_dataframe(
    *,
    year: int,
    month: int,
    day_block: int,
    id_conagua: str | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    own_session = session is None
    session = session or _session()
    try:
        payload = _request_json(
            session,
            "js/funciones.php",
            data={"anio": year, "mes": month, "decena": day_block},
        )
    finally:
        if own_session:
            session.close()

    rows = [_normalize_portal_record(item) for item in payload]
    df = pd.DataFrame(rows)
    if id_conagua:
        df = df.loc[df["id_conagua"] == str(id_conagua)].reset_index(drop=True)
    return df


def fetch_series_dataframe(
    *,
    id_conagua: str,
    month: int,
    day_block: int,
    start_year: int,
    end_year: int,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    own_session = session is None
    session = session or _session()
    try:
        payload = _request_json(
            session,
            "js/graf.php",
            data={
                "idConagua": id_conagua,
                "anioInicial": start_year,
                "anioFinal": end_year,
                "mes": month,
                "decena": day_block,
            },
        )
    finally:
        if own_session:
            session.close()

    return pd.DataFrame([_normalize_portal_record(item) for item in payload])


def _read_query_sheet(config_path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for sheet_name in QUERY_SHEET_NAME_ALIASES:
        try:
            return pd.read_excel(config_path, sheet_name=sheet_name, engine="openpyxl")
        except ValueError as exc:
            last_error = exc

    available_sheets = pd.ExcelFile(config_path, engine="openpyxl").sheet_names
    available = ", ".join(available_sheets)
    raise ValueError(
        f"No se encontro la hoja de configuracion '{QUERY_SHEET_NAME}'. Hojas disponibles: {available}"
    ) from last_error


def _read_catalog_sheet(config_path: Path) -> pd.DataFrame | None:
    last_error: Exception | None = None
    for sheet_name in CATALOG_SHEET_NAME_ALIASES:
        try:
            return pd.read_excel(config_path, sheet_name=sheet_name, engine="openpyxl")
        except ValueError as exc:
            last_error = exc
    if last_error is not None:
        return None
    return None


def _validate_month(month: int) -> None:
    if month < 1 or month > 12:
        raise ValueError(f"Mes invalido: {month}. Usa un valor entre 1 y 12.")


def _validate_day_block(day_block: int) -> None:
    if day_block not in {1, 2, 3}:
        raise ValueError(f"Decena invalida: {day_block}. Usa 1, 2 o 3.")


def load_queries_config(config_path: Path) -> list[PresaQuery]:
    df = _read_query_sheet(config_path)
    df = df.rename(columns=lambda column: QUERY_COLUMN_ALIASES.get(str(column), str(column)))
    missing = [column for column in ("active", "query_name", "query_type", "year", "month", "day_block") if column not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas en '{QUERY_SHEET_NAME}': {', '.join(missing)}")
    if "dam_name" not in df.columns:
        df["dam_name"] = ""
    if "state" not in df.columns:
        df["state"] = ""

    configs: list[PresaQuery] = []
    for idx, row in df.dropna(how="all").iterrows():
        if not _parse_bool(row.get("active")):
            continue

        query_type = _clean_string(row.get("query_type")).lower()
        if query_type not in SUPPORTED_QUERY_TYPES:
            raise ValueError(
                f"Fila {idx + 2}: tipo_consulta invalido '{query_type}'. "
                f"Usa uno de: {', '.join(sorted(SUPPORTED_QUERY_TYPES))}"
            )

        year = _parse_optional_int(row.get("year"))
        month = _parse_optional_int(row.get("month"))
        day_block = _parse_optional_int(row.get("day_block"))
        if year is None or month is None or day_block is None:
            raise ValueError(f"Fila {idx + 2}: anio, mes y decena son obligatorios.")
        _validate_month(month)
        _validate_day_block(day_block)

        end_year_raw = row.get("end_year")
        end_year_explicit = _is_explicit_value(end_year_raw)
        end_year = _parse_optional_int(end_year_raw) or year
        start_year = _parse_optional_int(row.get("start_year"))
        range_end_year: int | None = None
        if query_type == "presas_periodo" and end_year_explicit:
            if end_year < year:
                raise ValueError(
                    f"Fila {idx + 2}: anio_final ({end_year}) no puede ser menor que anio ({year}) "
                    "para presas_periodo."
                )
            range_end_year = end_year
        if query_type == "serie_presa":
            if not _clean_string(row.get("id_conagua")) and not _clean_string(row.get("dam_name")):
                raise ValueError(
                    f"Fila {idx + 2}: id_conagua o nombre_oficial es obligatorio para serie_presa."
                )
            if start_year is None:
                start_year = max(end_year - 9, 1999)
            if start_year > end_year:
                raise ValueError(f"Fila {idx + 2}: anio_inicial no puede ser mayor que anio_final.")
        elif query_type == "presas_estado":
            if not _clean_string(row.get("state")):
                raise ValueError(f"Fila {idx + 2}: estado es obligatorio para presas_estado.")
            if start_year is not None and start_year > end_year:
                raise ValueError(f"Fila {idx + 2}: anio_inicial no puede ser mayor que anio_final.")
        elif start_year is not None and start_year > end_year:
            raise ValueError(f"Fila {idx + 2}: anio_inicial no puede ser mayor que anio_final.")

        configs.append(
            PresaQuery(
                row_number=idx + 2,
                query_name=_clean_string(row.get("query_name")) or f"consulta_{idx + 2}",
                query_type=query_type,
                id_conagua=_clean_string(row.get("id_conagua")) or None,
                year=year,
                month=month,
                day_block=day_block,
                start_year=start_year,
                end_year=end_year,
                range_end_year=range_end_year,
                dam_name=_clean_string(row.get("dam_name")) or None,
                state=_clean_string(row.get("state")) or None,
            )
        )

    return configs


def _rename_columns(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    renamed = df.copy()
    renamed.columns = [column_map.get(str(column), str(column)) for column in renamed.columns]
    return renamed


def build_default_config_dataframe(
    *,
    default_year: int,
    default_month: int,
    default_day_block: int,
) -> pd.DataFrame:
    start_year = max(default_year - 9, 1999)
    return pd.DataFrame(
        [
            {
                "active": True,
                "query_name": "corte_nacional_actual",
                "query_type": "presas_periodo",
                "id_conagua": "",
                "year": default_year,
                "month": default_month,
                "day_block": default_day_block,
                "start_year": "",
                "end_year": "",
                "dam_name": "",
                "state": "",
            },
            {
                "active": True,
                "query_name": "presas_tamaulipas_actual",
                "query_type": "presas_estado",
                "id_conagua": "",
                "year": default_year,
                "month": default_month,
                "day_block": default_day_block,
                "start_year": "",
                "end_year": default_year,
                "dam_name": "",
                "state": "Tamaulipas",
            },
            {
                "active": True,
                "query_name": "serie_pedro_jose_mendez",
                "query_type": "serie_presa",
                "id_conagua": "3524",
                "year": default_year,
                "month": default_month,
                "day_block": default_day_block,
                "start_year": start_year,
                "end_year": default_year,
                "dam_name": "Pedro José Méndez",
                "state": "Tamaulipas",
            },
        ]
    )


def build_instructions_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "campo": "activo",
                "descripcion": "TRUE/FALSE. Solo se ejecutan las filas activas.",
            },
            {
                "campo": "nombre_consulta",
                "descripcion": "Nombre libre para identificar la consulta en las salidas.",
            },
            {
                "campo": "tipo_consulta",
                "descripcion": "Usa 'presas_periodo' para el corte nacional, 'presas_estado' para un lote por entidad, o 'serie_presa' para el historico de una presa.",
            },
            {
                "campo": "id_conagua",
                "descripcion": "Opcional si llenas nombre_oficial. En presas_periodo filtra una sola presa; en serie_presa apunta al historico.",
            },
            {
                "campo": "nombre_oficial / estado",
                "descripcion": "nombre_oficial + estado sirven para resolver id_conagua desde catalogo_presas. En presas_estado, estado es el filtro obligatorio.",
            },
            {
                "campo": "anio / mes / decena",
                "descripcion": "Periodo objetivo. Decena: 1=10, 2=20, 3=fin de mes.",
            },
            {
                "campo": "anio_inicial / anio_final",
                "descripcion": (
                    "Para serie_presa: rango historico; si anio_inicial queda vacio, usa una ventana de 10 anios. "
                    "Para presas_periodo: si anio_final esta lleno, obtiene todos los cortes desde anio/mes/decena "
                    "hasta el fin de ese anio (limitado al ultimo periodo publicado cuando corresponde)."
                ),
            },
        ]
    )


def _period_sort_value(year: Any, month: Any, day_block: Any) -> int:
    year_i = _parse_optional_int(year) or 0
    month_i = _parse_optional_int(month) or 0
    day_i = _parse_optional_int(day_block) or 0
    return year_i * 1000 + month_i * 10 + day_i


def _advance_period(year: int, month: int, day_block: int) -> tuple[int, int, int]:
    if day_block < 3:
        return year, month, day_block + 1
    if month < 12:
        return year, month + 1, 1
    return year + 1, 1, 1


def _iter_forward_periods(
    *,
    start_year: int,
    start_month: int,
    start_day_block: int,
    end_year: int,
    cap_period: dict[str, int] | None = None,
) -> list[tuple[int, int, int]]:
    """Genera periodos consecutivos desde el inicio hasta fin de `end_year`, opcionalmente acotado al portal."""
    end_sort = _period_sort_value(end_year, 12, 3)
    cap_sort = (
        _period_sort_value(cap_period["year"], cap_period["month"], cap_period["day_block"])
        if cap_period is not None
        else end_sort
    )
    max_sort = min(end_sort, cap_sort)
    start_sort = _period_sort_value(start_year, start_month, start_day_block)
    if start_sort > max_sort:
        return []

    periods: list[tuple[int, int, int]] = []
    year, month, day_block = start_year, start_month, start_day_block
    while _period_sort_value(year, month, day_block) <= max_sort:
        periods.append((year, month, day_block))
        year, month, day_block = _advance_period(year, month, day_block)
    return periods


def build_catalog_dataframe(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    catalog_columns = [
        "id_conagua",
        "nombre_oficial",
        "nombre_comun",
        "estado",
        "municipio",
        "uso_principal",
        "distrito_riego",
        "latitud",
        "longitud",
        "detalle_presa_url",
        "anio",
        "mes",
        "decena",
    ]
    available = [column for column in catalog_columns if column in snapshot_df.columns]
    catalog_df = snapshot_df[available].copy()
    if catalog_df.empty:
        return catalog_df

    catalog_df["_period_sort"] = catalog_df.apply(
        lambda row: _period_sort_value(row.get("anio"), row.get("mes"), row.get("decena")),
        axis=1,
    )
    catalog_df = catalog_df.sort_values(["id_conagua", "_period_sort"], ascending=[True, False], na_position="last")

    latest_df = catalog_df.drop_duplicates(subset=["id_conagua"], keep="first").drop(columns="_period_sort")
    earliest_df = (
        catalog_df.sort_values(["id_conagua", "_period_sort"], ascending=[True, True], na_position="last")
        .drop_duplicates(subset=["id_conagua"], keep="first")
        .rename(
            columns={
                "anio": "first_seen_year",
                "mes": "first_seen_month",
                "decena": "first_seen_day_block",
            }
        )[["id_conagua", "first_seen_year", "first_seen_month", "first_seen_day_block"]]
    )
    latest_period_df = latest_df.rename(
        columns={
            "anio": "last_seen_year",
            "mes": "last_seen_month",
            "decena": "last_seen_day_block",
        }
    )[["id_conagua", "last_seen_year", "last_seen_month", "last_seen_day_block"]]
    counts_df = (
        catalog_df.groupby("id_conagua", dropna=False)
        .size()
        .reset_index(name="periods_seen_count")
    )
    summary_df = counts_df.merge(earliest_df, on="id_conagua", how="left").merge(
        latest_period_df,
        on="id_conagua",
        how="left",
    )

    merged_df = latest_df.merge(summary_df, on="id_conagua", how="left")
    merged_df = merged_df.sort_values(["estado", "nombre_oficial", "id_conagua"], na_position="last").reset_index(drop=True)
    return merged_df


def _iter_catalog_periods(
    *,
    years: list[int],
    scope: str,
    default_period: dict[str, int],
) -> list[tuple[int, int, int]]:
    if scope == "latest":
        return []
    if scope != "all-available":
        raise ValueError(f"catalog_scope invalido: {scope}")

    periods: list[tuple[int, int, int]] = []
    max_year = default_period["year"]
    max_month = default_period["month"]
    max_day_block = default_period["day_block"]

    for year in sorted(set(years), reverse=True):
        month_start = 12
        month_end = 1
        if year == max_year:
            month_start = max_month
        for month in range(month_start, month_end - 1, -1):
            day_blocks = (3, 2, 1)
            if year == max_year and month == max_month:
                day_blocks = tuple(block for block in (3, 2, 1) if block <= max_day_block)
            for day_block in day_blocks:
                periods.append((year, month, day_block))
    return periods


def build_catalog_snapshot_union(
    *,
    session: requests.Session,
    scope: str,
    default_period: dict[str, int],
    available_years: list[int],
) -> pd.DataFrame:
    latest_snapshot = fetch_snapshot_dataframe(
        year=default_period["year"],
        month=default_period["month"],
        day_block=default_period["day_block"],
        session=session,
    )
    if scope == "latest":
        return latest_snapshot

    frames: list[pd.DataFrame] = [latest_snapshot]
    seen_periods = {
        (default_period["year"], default_period["month"], default_period["day_block"])
    }
    periods = _iter_catalog_periods(
        years=available_years,
        scope=scope,
        default_period=default_period,
    )
    total = len(periods)
    for idx, (year, month, day_block) in enumerate(periods, start=1):
        if (year, month, day_block) in seen_periods:
            continue
        try:
            snapshot_df = fetch_snapshot_dataframe(
                year=year,
                month=month,
                day_block=day_block,
                session=session,
            )
        except Exception as exc:
            LOGGER.warning(
                "No se pudo agregar el periodo %s-%02d decena %s al catalogo: %s",
                year,
                month,
                day_block,
                exc,
            )
            continue

        if not snapshot_df.empty:
            frames.append(snapshot_df)
        seen_periods.add((year, month, day_block))
        if idx % 100 == 0 or idx == total:
            LOGGER.info(
                "Construyendo catalogo maestro: %s/%s periodos revisados, %s snapshots acumulados",
                idx,
                total,
                len(frames),
            )

    return pd.concat(frames, ignore_index=True) if frames else latest_snapshot


def _resolve_id_from_catalog(query: PresaQuery, catalog_df: pd.DataFrame) -> str:
    if query.id_conagua:
        return query.id_conagua
    if query.query_type in {"presas_periodo", "presas_estado"} and not query.dam_name:
        return ""
    if not query.dam_name:
        raise ValueError("La consulta requiere id_conagua o nombre_oficial.")

    working = catalog_df.copy()
    working["_dam_name_norm"] = working["nombre_oficial"].map(_slug_text)
    working["_state_norm"] = working["estado"].map(_slug_text)
    dam_name_norm = _slug_text(query.dam_name)
    state_norm = _slug_text(query.state)

    if state_norm:
        working = working.loc[working["_state_norm"] == state_norm]
    exact = working.loc[working["_dam_name_norm"] == dam_name_norm]
    if len(exact) == 1:
        return str(exact.iloc[0]["id_conagua"])
    if len(exact) > 1:
        ids = ", ".join(exact["id_conagua"].astype(str).tolist()[:10])
        raise ValueError(
            f"nombre_oficial='{query.dam_name}' coincide con multiples presas. "
            f"Agrega estado o usa id_conagua. Coincidencias: {ids}"
        )

    contains = working.loc[working["_dam_name_norm"].str.contains(re.escape(dam_name_norm), na=False)]
    if len(contains) == 1:
        return str(contains.iloc[0]["id_conagua"])
    if len(contains) > 1:
        sample = ", ".join(
            f"{row.nombre_oficial} ({row.estado}) [{row.id_conagua}]"
            for row in contains[["nombre_oficial", "estado", "id_conagua"]].head(5).itertuples(index=False)
        )
        raise ValueError(
            f"nombre_oficial='{query.dam_name}' tiene multiples coincidencias en el catalogo. "
            f"Agrega estado o usa id_conagua. Ejemplos: {sample}"
        )

    raise ValueError(
        f"No se encontro una presa para nombre_oficial='{query.dam_name}'"
        + (f" y estado='{query.state}'." if query.state else ".")
    )


def create_default_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    overwrite: bool = False,
    catalog_scope: str = "latest",
) -> Path:
    if config_path.exists() and not overwrite:
        return config_path

    session = _session()
    try:
        available_years = fetch_available_years(session)
        default_period = fetch_default_period(session)
        catalog_snapshot = build_catalog_snapshot_union(
            session=session,
            scope=catalog_scope,
            default_period=default_period,
            available_years=available_years,
        )
    finally:
        session.close()

    config_path.parent.mkdir(parents=True, exist_ok=True)
    queries_df = build_default_config_dataframe(
        default_year=default_period["year"],
        default_month=default_period["month"],
        default_day_block=default_period["day_block"],
    )
    instructions_df = build_instructions_dataframe()
    catalog_df = build_catalog_dataframe(catalog_snapshot)

    with pd.ExcelWriter(config_path, engine="openpyxl") as writer:
        _rename_columns(queries_df, QUERY_EXPORT_COLUMN_MAP).to_excel(
            writer,
            sheet_name=QUERY_SHEET_NAME,
            index=False,
        )
        _rename_columns(instructions_df, INSTRUCTIONS_EXPORT_COLUMN_MAP).to_excel(
            writer,
            sheet_name=INSTRUCTIONS_SHEET_NAME,
            index=False,
        )
        _rename_columns(catalog_df, CATALOG_EXPORT_COLUMN_MAP).to_excel(
            writer,
            sheet_name=CATALOG_SHEET_NAME,
            index=False,
        )

    return config_path


def _assign_snapshot_metadata(
    snapshot_df: pd.DataFrame,
    *,
    query: PresaQuery,
    resolved_id_conagua: str,
    period_year: int,
    period_month: int,
    period_day_block: int,
    extracted_at: str,
) -> pd.DataFrame:
    return snapshot_df.assign(
        config_row_number=query.row_number,
        query_name=query.query_name,
        query_type=query.query_type,
        requested_id_conagua=resolved_id_conagua or "",
        requested_state=query.state or "",
        query_year=period_year,
        query_month=period_month,
        query_day_block=period_day_block,
        fuente="presas_agricolas_portal",
        fecha_extraccion=extracted_at,
    )


def _fetch_snapshot_for_period(
    query: PresaQuery,
    *,
    period_year: int,
    period_month: int,
    period_day_block: int,
    session: requests.Session,
    resolved_id_conagua: str,
) -> pd.DataFrame:
    snapshot_df = fetch_snapshot_dataframe(
        year=period_year,
        month=period_month,
        day_block=period_day_block,
        id_conagua=resolved_id_conagua if resolved_id_conagua else None,
        session=session,
    )
    snapshot_df = _filter_snapshot_by_state(snapshot_df, query.state)
    if snapshot_df.empty and resolved_id_conagua:
        raise RuntimeError(
            f"No se encontro la presa {resolved_id_conagua} para el periodo "
            f"{period_year}-{period_month:02d} decena {period_day_block}."
        )
    if snapshot_df.empty and query.state:
        raise RuntimeError(
            f"No se encontraron presas para estado='{query.state}' en el periodo "
            f"{period_year}-{period_month:02d} decena {period_day_block}."
        )
    return snapshot_df


def _execute_query(
    query: PresaQuery,
    *,
    session: requests.Session,
    extracted_at: str,
    resolved_id_conagua: str,
    published_period: dict[str, int] | None = None,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    if query.query_type == "presas_periodo" and query.range_end_year is not None:
        periods = _iter_forward_periods(
            start_year=query.year,
            start_month=query.month,
            start_day_block=query.day_block,
            end_year=query.range_end_year,
            cap_period=published_period,
        )
        if not periods:
            raise RuntimeError(
                f"El rango solicitado para '{query.query_name}' queda fuera de los periodos publicados."
            )

        frames: list[pd.DataFrame] = []
        period_errors: list[str] = []
        total = len(periods)
        for idx, (period_year, period_month, period_day_block) in enumerate(periods, start=1):
            try:
                snapshot_df = _fetch_snapshot_for_period(
                    query,
                    period_year=period_year,
                    period_month=period_month,
                    period_day_block=period_day_block,
                    session=session,
                    resolved_id_conagua=resolved_id_conagua,
                )
            except Exception as exc:
                period_errors.append(
                    f"{period_year}-{period_month:02d} decena {period_day_block}: {exc}"
                )
                LOGGER.warning(
                    "Fallo el corte %s-%02d decena %s en consulta %s: %s",
                    period_year,
                    period_month,
                    period_day_block,
                    query.query_name,
                    exc,
                )
                continue

            frames.append(
                _assign_snapshot_metadata(
                    snapshot_df,
                    query=query,
                    resolved_id_conagua=resolved_id_conagua,
                    period_year=period_year,
                    period_month=period_month,
                    period_day_block=period_day_block,
                    extracted_at=extracted_at,
                )
            )
            if idx % 12 == 0 or idx == total:
                LOGGER.info(
                    "Consulta %s: %s/%s periodos descargados",
                    query.query_name,
                    idx,
                    total,
                )

        if not frames:
            raise RuntimeError(
                f"No se pudo obtener ningun corte para '{query.query_name}'. Errores: "
                + "; ".join(period_errors[:5])
            )
        if period_errors:
            LOGGER.warning(
                "Consulta %s completa con %s periodo(s) fallido(s) de %s",
                query.query_name,
                len(period_errors),
                total,
            )
        return pd.concat(frames, ignore_index=True), None

    if query.query_type in {"presas_periodo", "presas_estado"}:
        snapshot_df = _fetch_snapshot_for_period(
            query,
            period_year=query.year,
            period_month=query.month,
            period_day_block=query.day_block,
            session=session,
            resolved_id_conagua=resolved_id_conagua,
        )
        snapshot_df = _assign_snapshot_metadata(
            snapshot_df,
            query=query,
            resolved_id_conagua=resolved_id_conagua,
            period_year=query.year,
            period_month=query.month,
            period_day_block=query.day_block,
            extracted_at=extracted_at,
        )
        return snapshot_df, None

    series_df = fetch_series_dataframe(
        id_conagua=resolved_id_conagua,
        month=query.month,
        day_block=query.day_block,
        start_year=query.start_year or max(query.year - 9, 1999),
        end_year=query.end_year or query.year,
        session=session,
    )
    if series_df.empty:
        raise RuntimeError(f"No se encontro informacion historica para la presa {query.id_conagua}.")
    series_df = series_df.assign(
        config_row_number=query.row_number,
        query_name=query.query_name,
        query_type=query.query_type,
        query_year=query.year,
        query_month=query.month,
        query_day_block=query.day_block,
        query_start_year=query.start_year or max(query.year - 9, 1999),
        query_end_year=query.end_year or query.year,
        fuente="presas_agricolas_portal",
        fecha_extraccion=extracted_at,
    )
    return None, series_df


def run_from_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    output_path: Path | None = None,
) -> Path:
    configure_logging()
    if not config_path.exists():
        create_default_config(config_path)

    queries = load_queries_config(config_path)
    years = fetch_available_years()
    extracted_at = datetime.now().isoformat(timespec="seconds")
    catalog_sheet_df = _read_catalog_sheet(config_path)
    if catalog_sheet_df is None:
        default_period = fetch_default_period()
        catalog_sheet_df = fetch_snapshot_dataframe(
            year=default_period["year"],
            month=default_period["month"],
            day_block=default_period["day_block"],
        )
    catalog_df = catalog_sheet_df.rename(
        columns=lambda column: {
            "id_conagua": "id_conagua",
            "nombre_oficial": "nombre_oficial",
            "nombre_comun": "nombre_comun",
            "estado": "estado",
        }.get(str(column), str(column))
    )

    snapshot_frames: list[pd.DataFrame] = []
    series_frames: list[pd.DataFrame] = []
    errors: list[dict[str, Any]] = []

    session = _session()
    try:
        published_period = fetch_default_period(session)
        for query in queries:
            try:
                resolved_id = _resolve_id_from_catalog(query, catalog_df)
                snapshot_df, series_df = _execute_query(
                    query,
                    session=session,
                    extracted_at=extracted_at,
                    resolved_id_conagua=resolved_id,
                    published_period=published_period,
                )
                if snapshot_df is not None:
                    snapshot_frames.append(snapshot_df)
                if series_df is not None:
                    series_frames.append(series_df)
            except Exception as exc:  # pragma: no cover - handled by workbook output
                LOGGER.exception("Fallo la consulta %s", query.query_name)
                errors.append(
                    {
                        "config_row_number": query.row_number,
                        "query_name": query.query_name,
                        "query_type": query.query_type,
                        "error": str(exc),
                    }
                )
    finally:
        session.close()

    snapshots_df = (
        pd.concat(snapshot_frames, ignore_index=True)
        if snapshot_frames
        else pd.DataFrame(columns=list(SNAPSHOT_COLUMN_MAP))
    )
    series_df = (
        pd.concat(series_frames, ignore_index=True)
        if series_frames
        else pd.DataFrame(columns=list(SERIES_COLUMN_MAP))
    )
    errors_df = pd.DataFrame(errors, columns=list(ERROR_COLUMN_MAP))
    meta_df = pd.DataFrame(
        [
            {
                "config_path": str(config_path.resolve()),
                "executed_at": extracted_at,
                "queries_attempted": len(queries),
                "queries_succeeded": len(queries) - len(errors),
                "queries_failed": len(errors),
                "available_year_min": min(years),
                "available_year_max": max(years),
            }
        ]
    )

    if output_path is None:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_OUTPUT_DIR / f"presas_agricolas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        _rename_columns(snapshots_df, SNAPSHOT_COLUMN_MAP).to_excel(writer, sheet_name="presas_periodo", index=False)
        _rename_columns(series_df, SERIES_COLUMN_MAP).to_excel(writer, sheet_name="series_presa", index=False)
        _rename_columns(errors_df, ERROR_COLUMN_MAP).to_excel(writer, sheet_name="errores", index=False)
        _rename_columns(meta_df, META_COLUMN_MAP).to_excel(writer, sheet_name="metadatos", index=False)

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrae datos del portal de Presas Agricolas.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Workbook de configuracion. Default: {DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta de salida .xlsx. Si se omite, guarda en data/raw/presas_agricolas/ con timestamp.",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Crea el workbook de configuracion con valores por defecto y termina.",
    )
    parser.add_argument(
        "--overwrite-config",
        action="store_true",
        help="Permite sobrescribir el workbook de configuracion al usar --init-config.",
    )
    parser.add_argument(
        "--catalog-scope",
        choices=("latest", "all-available"),
        default="latest",
        help="Al crear el workbook, usa solo el ultimo corte o intenta un catalogo maestro uniendo todos los periodos disponibles.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    if args.init_config:
        path = create_default_config(
            args.config,
            overwrite=args.overwrite_config,
            catalog_scope=args.catalog_scope,
        )
        LOGGER.info("Workbook de configuracion listo en %s", path)
        return

    output_path = run_from_config(args.config, output_path=args.output)
    LOGGER.info("Extraccion completada en %s", output_path)


if __name__ == "__main__":
    main()
