"""Scraper HTTP (sin navegador) para Avance Agricola SIAP.

Flujo implementado:
1) Abre la página principal para establecer cookies de sesión.
2) Reproduce llamadas xajax para poblar combos y ejecutar `reporte`.
3) Descarga el reporte desde `Clases/reporte.php`.

La interfaz pública expone tres filtros de usuario:
- year
- month
- crop

El resto de las opciones se fija al flujo pedido por el usuario:
- Tipo de reporte: Por ubicación geográfica
- Desglose: Por entidad federativa
- Ciclo: Ciclicos - Perennes
- Modalidad: Riego + Temporal
- Entidad federativa: Nacional
- Tipo de agricultura / producción / mercado: Todo
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.extract.spreadsheet_localization import AVANCE_EXPORT_COLUMN_MAP, rename_columns

BASE_URL = "https://nube.agricultura.gob.mx/avance_agricola/"
REPORTE_XLS_URL = BASE_URL + "Clases/reporte.php"
DEFAULT_TIMEOUT = 90

LOGGER = logging.getLogger("avance_agricola_http")
REPORT_COLUMN_ALIASES = {
    "entidad": "entidad",
    "superficie_ha_sembrada": "superficie_sembrada_ha",
    "superficie_ha_cosechada": "superficie_cosechada_ha",
    "superficie_ha_siniestrada": "superficie_siniestrada_ha",
    "produccion": "produccion",
    "rendimiento_udm_ha": "rendimiento_udm_ha",
}
MOJIBAKE_REPLACEMENTS = {
    "ÃƒÂ¡": "a",
    "ÃƒÂ©": "e",
    "ÃƒÂ­": "i",
    "ÃƒÂ³": "o",
    "ÃƒÂº": "u",
    "ÃƒÂ±": "n",
    "ÃƒÂ": "a",
    "Ãƒâ€°": "e",
    "ÃƒÂ": "i",
    "Ãƒâ€œ": "o",
    "ÃƒÅ¡": "u",
    "Ãƒâ€˜": "n",
}

FIXED_LABELS = {
    "tipo_reporte": "1",
    "ciclo": "Ciclicos - Perennes",
    "modalidad": "Riego + Temporal",
    "entidad": "Nacional",
    "opcion_ddr_mpio": "2",
    "agric": "Todo",
    "tiprod": "Todo",
    "timerc": "Todo",
}


@dataclass
class Option:
    value: str
    label: str
    selected: bool = False


@dataclass
class XajaxResult:
    response_text: str
    commands: list[dict[str, Any]]


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s")


def ensure_ok_response(response: requests.Response, context: str) -> None:
    if response.status_code >= 400:
        raise RuntimeError(f"{context} falló: HTTP {response.status_code}")


def get_initial_page(session: requests.Session) -> str:
    LOGGER.info("GET inicial: %s", BASE_URL)
    response = session.get(BASE_URL, timeout=DEFAULT_TIMEOUT)
    ensure_ok_response(response, "GET inicial")
    return response.text


def _dump_debug(debug_dir: Path | None, name: str, content: str) -> None:
    if not debug_dir:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / name
    path.write_text(content, encoding="utf-8")
    LOGGER.debug("Dump debug guardado: %s", path)


def _xajax_payload(function_name: str, args: list[Any]) -> dict[str, Any]:
    return {
        "xajax": function_name,
        "xajaxr": f"{time.time():.6f}",
        "xajaxargs[]": [str(arg) for arg in args],
    }


def xajax_call(
    session: requests.Session,
    function_name: str,
    args: list[Any],
    *,
    debug_dir: Path | None = None,
    call_index: int = 0,
) -> XajaxResult:
    payload = _xajax_payload(function_name, args)
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE_URL,
    }
    LOGGER.debug("xajax_call %s args=%s", function_name, args)
    response = session.post(BASE_URL, data=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
    ensure_ok_response(response, f"xajax {function_name}")
    text = response.text
    _dump_debug(debug_dir, f"{call_index:03d}_{function_name}.xml", text)
    return XajaxResult(response_text=text, commands=parse_xajax_commands(text))


def parse_xajax_commands(xml_text: str) -> list[dict[str, Any]]:
    xml_text = xml_text.strip()
    if not xml_text:
        return []

    commands: list[dict[str, Any]] = []
    try:
        root = ElementTree.fromstring(xml_text)
        for cmd in root.findall(".//cmd"):
            commands.append(
                {
                    "n": cmd.attrib.get("n", ""),
                    "t": cmd.attrib.get("t", ""),
                    "p": cmd.attrib.get("p", ""),
                    "data": "".join(cmd.itertext()),
                }
            )
        return commands
    except ElementTree.ParseError:
        cdata_blocks = re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml_text, flags=re.DOTALL)
        return [{"n": "unknown", "t": "", "p": "", "data": block} for block in cdata_blocks]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _extract_options_from_html(html: str) -> list[Option]:
    soup = BeautifulSoup(html, "html.parser")
    options: list[Option] = []
    for opt in soup.select("option"):
        label = opt.get_text(" ", strip=True)
        if not label:
            continue
        options.append(
            Option(
                value=(opt.get("value") or "").strip(),
                label=label,
                selected=opt.has_attr("selected"),
            )
        )
    return options


def extract_options_from_commands(commands: list[dict[str, Any]], target_ids: set[str]) -> list[Option]:
    for cmd in commands:
        target = (cmd.get("t") or "").strip()
        prop = (cmd.get("p") or "").strip()
        if target in target_ids and prop == "innerHTML":
            options = _extract_options_from_html(cmd.get("data", ""))
            if options:
                return options
    return []


def parse_defaults_from_page(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    defaults: dict[str, str] = {}
    keys = [
        "tipo-reporte",
        "anioagric",
        "mesagric",
        "cicloProd",
        "modalidad",
        "entidad",
        "distrito",
        "municipio",
        "cultivo",
        "unidMed",
        "variedad",
        "opcionDDRMpio",
        "agric",
        "tiprod",
        "timerc",
    ]

    for key in keys:
        tag = soup.find(id=key)
        if tag is None:
            tag = soup.find(attrs={"name": key})
        if tag is None:
            defaults[key] = ""
            continue

        if tag.name == "select":
            selected = tag.find("option", selected=True) or tag.find("option")
            defaults[key] = (selected.get("value") if selected else "") or ""
        elif tag.get("type") == "radio":
            checked = soup.find(attrs={"name": key, "checked": True})
            defaults[key] = (checked.get("value") if checked else tag.get("value") or "").strip()
        else:
            defaults[key] = (tag.get("value") or "").strip()

    return defaults


def _pick_default_from_options(
    options: list[Option],
    *,
    prefer_non_empty: bool = True,
    allow_blank_when_multiselect: bool = False,
) -> str:
    if not options:
        return ""

    selected_values = [opt.value for opt in options if opt.selected]
    if allow_blank_when_multiselect and len(selected_values) > 1:
        return ""
    if selected_values:
        for value in selected_values:
            if value or not prefer_non_empty:
                return value

    for option in options:
        if option.value or not prefer_non_empty:
            return option.value
    return options[0].value


def _extract_value_from_js_assignment(js_text: str) -> str | None:
    patterns = [
        r"\.value\s*=\s*'([^']*)'",
        r"\.value\s*=\s*\"([^\"]*)\"",
        r"\.selectedIndex\s*=\s*([0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, js_text)
        if match:
            return match.group(1)
    return None


def _update_state_from_innerhtml_commands(
    state: dict[str, str],
    commands: list[dict[str, Any]],
    target_map: dict[str, set[str]],
) -> None:
    for field_name, target_ids in target_map.items():
        options = extract_options_from_commands(commands, target_ids)
        if not options:
            continue

        allow_blank = field_name in {"cicloProd", "modalidad"}
        chosen = _pick_default_from_options(options, allow_blank_when_multiselect=allow_blank)
        if field_name not in state or not state[field_name]:
            state[field_name] = chosen


def _update_state_from_js_commands(
    state: dict[str, str],
    commands: list[dict[str, Any]],
    id_to_field: dict[str, str],
) -> None:
    for cmd in commands:
        if (cmd.get("n") or "").strip() != "js":
            continue
        js = cmd.get("data", "")
        for element_id, field_name in id_to_field.items():
            if element_id not in js:
                continue
            extracted = _extract_value_from_js_assignment(js)
            if extracted is not None:
                state[field_name] = extracted


def find_option_value(options: list[Option], wanted_label: str, field_name: str) -> str:
    wanted_norm = _normalize_text(wanted_label)

    exact = [opt for opt in options if _normalize_text(opt.label) == wanted_norm]
    if exact:
        return exact[0].value

    exact_value = [opt for opt in options if opt.value == wanted_label]
    if exact_value:
        return exact_value[0].value

    contains = [opt for opt in options if wanted_norm in _normalize_text(opt.label)]
    if len(contains) == 1:
        return contains[0].value

    sample = ", ".join(f"{option.label}({option.value})" for option in options[:10])
    raise ValueError(
        f"No se encontró coincidencia única para {field_name}='{wanted_label}'. "
        f"Opciones ejemplo: {sample}"
    )


def _load_options_for_field(
    session: requests.Session,
    function_name: str,
    args: list[str | int],
    target_field: str,
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> list[Option]:
    call_counter[0] += 1
    result = xajax_call(
        session,
        function_name,
        args,
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    options = extract_options_from_commands(result.commands, {target_field})
    if not options:
        raise RuntimeError(
            f"No fue posible extraer opciones de {target_field} desde xajax_{function_name}"
        )
    return options


def _load_bootstrap_options(
    session: requests.Session,
    base_defaults: dict[str, str],
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> dict[str, str]:
    state = dict(base_defaults)
    target_map = {
        "anioagric": {"anioagric"},
        "cicloProd": {"cicloProd"},
        "modalidad": {"modalidad"},
        "entidad": {"entidad"},
        "agric": {"agric"},
        "tiprod": {"tiprod"},
        "timerc": {"timerc"},
    }
    id_to_field = {key: key for key in target_map}
    bootstrap_calls: list[tuple[str, list[str | int]]] = [
        ("llenaAnios", []),
        ("llenaCiclo", []),
        ("llenaModa", []),
        ("llenaEntidades", []),
        ("llenaTipoAgric", [0]),
        ("llenaTipoProd", [0]),
        ("llenaTipoMerc", [0]),
    ]

    for function_name, args in bootstrap_calls:
        call_counter[0] += 1
        result = xajax_call(
            session,
            function_name,
            args,
            debug_dir=debug_dir,
            call_index=call_counter[0],
        )
        _update_state_from_innerhtml_commands(state, result.commands, target_map)
        _update_state_from_js_commands(state, result.commands, id_to_field)
    return state


def _load_location_options(
    session: requests.Session,
    state: dict[str, str],
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> dict[str, str]:
    target_map = {
        "distrito": {"distrito"},
        "municipio": {"municipio"},
    }
    id_to_field = {key: key for key in target_map}
    location_calls: list[tuple[str, list[str | int]]] = [
        ("llenaDistrito", [state["entidad"]]),
        ("cargaMuni", [state["entidad"], 0]),
    ]

    for function_name, args in location_calls:
        call_counter[0] += 1
        result = xajax_call(
            session,
            function_name,
            args,
            debug_dir=debug_dir,
            call_index=call_counter[0],
        )
        _update_state_from_innerhtml_commands(state, result.commands, target_map)
        _update_state_from_js_commands(state, result.commands, id_to_field)

    if not state.get("distrito"):
        state["distrito"] = "0"
    if not state.get("municipio"):
        state["municipio"] = "0"
    return state


def _load_crop_dependent_options(
    session: requests.Session,
    state: dict[str, str],
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> dict[str, str]:
    target_map = {
        "unidMed": {"unidMed"},
        "variedad": {"variedad"},
    }
    id_to_field = {key: key for key in target_map}

    call_counter[0] += 1
    unit_result = xajax_call(
        session,
        "llenaUnidMed",
        [state["cultivo"]],
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    _update_state_from_innerhtml_commands(state, unit_result.commands, target_map)
    _update_state_from_js_commands(state, unit_result.commands, id_to_field)
    if not state.get("unidMed"):
        state["unidMed"] = "0"

    call_counter[0] += 1
    variety_result = xajax_call(
        session,
        "llenaVariedad",
        [state["cultivo"], state["unidMed"]],
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    _update_state_from_innerhtml_commands(state, variety_result.commands, target_map)
    _update_state_from_js_commands(state, variety_result.commands, id_to_field)
    if not state.get("variedad"):
        state["variedad"] = "0"

    return state


def submit_report(
    session: requests.Session,
    params: dict[str, str],
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> None:
    ordered = [
        "tipo-reporte",
        "anioagric",
        "cicloProd",
        "modalidad",
        "entidad",
        "distrito",
        "municipio",
        "cultivo",
        "unidMed",
        "variedad",
        "opcionDDRMpio",
        "agric",
        "tiprod",
        "timerc",
        "mesagric",
    ]
    args = [params.get(key, "") for key in ordered]

    call_counter[0] += 1
    result = xajax_call(
        session,
        "reporte",
        args,
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    if not result.commands:
        raise RuntimeError("xajax_reporte no devolvió comandos; no se puede asegurar la generación")


def _looks_like_html(content: bytes) -> bool:
    prefix = content[:300].lower()
    return b"<html" in prefix or b"<!doctype html" in prefix


def _html_response_has_report(content: bytes) -> bool:
    text = content.decode("utf-8", errors="ignore").lower()
    return "resultados-reporte" in text or "<table" in text


def _html_response_has_error(content: bytes) -> bool:
    text = content.decode("utf-8", errors="ignore").lower()
    error_markers = [
        "undefined index: tabla",
        "<h1>sin datos</h1>",
        "warning",
        "notice",
        "fatal error",
    ]
    return any(marker in text for marker in error_markers)


def _resolve_output_path(output_path: Path, output_format: str) -> Path:
    expected_suffix = f".{output_format}"
    if output_path.suffix.lower() == expected_suffix:
        return output_path
    return output_path.with_suffix(expected_suffix)


def _fetch_report_content(session: requests.Session) -> bytes:
    LOGGER.info("Descargando reporte: %s", REPORTE_XLS_URL)
    response = session.get(REPORTE_XLS_URL, timeout=DEFAULT_TIMEOUT)
    ensure_ok_response(response, "Descarga de reporte.php")
    content = response.content
    content_type = (response.headers.get("Content-Type") or "").lower()

    if not content:
        raise RuntimeError("La descarga devolvió contenido vacío")

    if _looks_like_html(content):
        if _html_response_has_error(content) or not _html_response_has_report(content):
            preview = content[:500].decode("utf-8", errors="ignore")
            raise RuntimeError(
                "La descarga parece HTML de error (posible error de sesión/flujo). "
                f"Content-Type={content_type!r}. Preview={preview!r}"
            )
        LOGGER.info("El portal devolvió una tabla HTML compatible con Excel")

    return content


def _html_report_to_dataframe(content: bytes) -> pd.DataFrame:
    html = content.decode("utf-8", errors="ignore")
    tables = pd.read_html(StringIO(html))
    if not tables:
        raise RuntimeError("No se encontró ninguna tabla en la respuesta HTML del reporte")
    best_table = max(tables, key=lambda df: df.shape[0] * df.shape[1])
    if isinstance(best_table.columns, pd.MultiIndex):
        best_table.columns = [
            " ".join(str(part).strip() for part in col if str(part).strip() and str(part) != "nan").strip()
            for col in best_table.columns.to_flat_index()
        ]
    return best_table.dropna(how="all").reset_index(drop=True)


def _extract_report_header_metadata(html: str) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    crop_label_raw: str | None = None
    cutoff_label: str | None = None

    crop_match = re.search(r"Cultivo:\s*([^\n]+)", text, flags=re.IGNORECASE)
    if crop_match:
        crop_label_raw = re.sub(r"\s+", " ", crop_match.group(1)).strip() or None

    cutoff_match = re.search(r"(Situaci[oó]n al[^\n]+)", text, flags=re.IGNORECASE)
    if cutoff_match:
        cutoff_label = re.sub(r"\s+", " ", cutoff_match.group(1)).strip() or None

    return {
        "avance_crop_label_raw": crop_label_raw,
        "avance_unit_label": _extract_avance_unit_label(crop_label_raw),
        "report_cutoff_label": cutoff_label,
    }


def _extract_avance_unit_label(crop_label_raw: str | None) -> str | None:
    if not crop_label_raw:
        return None
    groups = re.findall(r"\(([^()]*)\)", crop_label_raw)
    if not groups:
        return None
    unit_candidate = groups[-1].strip()
    return unit_candidate or None


def _slugify_report_label(value: str) -> str:
    normalized = value
    for source, target in MOJIBAKE_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return re.sub(r"_+", "_", normalized).strip("_")


def _normalize_report_column_name(column: Any) -> str:
    parts = [str(part).strip() for part in column] if isinstance(column, tuple) else [str(column).strip()]
    cleaned_parts = [
        part
        for part in parts
        if part and part != "nan" and not part.lower().startswith("unnamed:")
    ]
    if not cleaned_parts:
        return "numero"
    combined = " ".join(dict.fromkeys(cleaned_parts))
    normalized = _slugify_report_label(combined)
    return REPORT_COLUMN_ALIASES.get(normalized, normalized or "columna")


def _normalize_report_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [_normalize_report_column_name(column) for column in normalized.columns]
    normalized = normalized.loc[:, ~normalized.columns.duplicated()].copy()

    numeric_columns = [
        "numero",
        "superficie_sembrada_ha",
        "superficie_cosechada_ha",
        "superficie_siniestrada_ha",
        "produccion",
        "rendimiento_udm_ha",
    ]
    for column in numeric_columns:
        if column in normalized.columns:
            try:
                normalized[column] = pd.to_numeric(normalized[column])
            except (TypeError, ValueError):
                continue
    return normalized


def _append_report_metadata(
    df: pd.DataFrame,
    *,
    year: str,
    month_value: str,
    month_label: str,
    crop: str,
    report_metadata: dict[str, str | None],
) -> pd.DataFrame:
    enriched = df.copy()
    enriched["avance_crop_label_raw"] = report_metadata.get("avance_crop_label_raw") or crop
    enriched["avance_unit_label"] = report_metadata.get("avance_unit_label")
    enriched["avance_crop_name"] = crop
    enriched["query_year"] = int(year)
    enriched["query_month"] = int(month_value)
    enriched["query_month_label"] = month_label
    enriched["report_cutoff_label"] = report_metadata.get("report_cutoff_label")
    enriched["source_name"] = "avance_agricola"
    return enriched


def _report_content_to_dataframe(
    content: bytes,
    *,
    year: str,
    month_value: str,
    month_label: str,
    crop: str,
) -> pd.DataFrame:
    html = content.decode("utf-8", errors="ignore")
    report_df = _normalize_report_dataframe(_html_report_to_dataframe(content))
    report_metadata = _extract_report_header_metadata(html)
    return _append_report_metadata(
        report_df,
        year=year,
        month_value=month_value,
        month_label=month_label,
        crop=crop,
        report_metadata=report_metadata,
    )


def _write_html_xls(df: pd.DataFrame, output_path: Path) -> None:
    output_path.write_text(df.to_html(index=False, na_rep="", border=1), encoding="utf-8")


def save_report(
    session: requests.Session,
    output_path: Path,
    output_format: str,
    *,
    year: str,
    month_value: str,
    month_label: str,
    crop: str,
) -> Path:
    resolved_output = _resolve_output_path(output_path, output_format)
    content = _fetch_report_content(session)
    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "xls" and not _looks_like_html(content):
        resolved_output.write_bytes(content)
        LOGGER.info("Archivo guardado: %s (%s bytes)", resolved_output, len(content))
        return resolved_output

    report_df = rename_columns(
        _report_content_to_dataframe(
            content,
            year=year,
            month_value=month_value,
            month_label=month_label,
            crop=crop,
        ),
        AVANCE_EXPORT_COLUMN_MAP,
    )
    if output_format == "csv":
        report_df.to_csv(resolved_output, index=False, encoding="utf-8-sig")
        LOGGER.info("CSV guardado: %s (%s filas)", resolved_output, len(report_df))
    elif output_format == "xlsx":
        report_df.to_excel(resolved_output, index=False, engine="openpyxl")
        LOGGER.info("XLSX guardado: %s (%s filas)", resolved_output, len(report_df))
    elif output_format == "xls":
        _write_html_xls(report_df, resolved_output)
        LOGGER.info("XLS guardado: %s (%s filas)", resolved_output, len(report_df))
    else:
        raise ValueError(f"Formato de salida no soportado: {output_format}")
    return resolved_output


def _default_output_path(year: str, month: str, crop: str) -> Path:
    crop_slug = _slugify_report_label(crop)
    month_slug = _slugify_report_label(month)
    return Path("data/raw/avance_agricola") / f"{crop_slug}_{year}_{month_slug}"


def prepare_report_session(
    year: str,
    month: str,
    crop: str,
    *,
    debug: bool,
    debug_dir: Path | None,
) -> tuple[requests.Session, str, str]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
    )

    call_counter = [0]
    initial_html = get_initial_page(session)
    _dump_debug(debug_dir, "000_initial_page.html", initial_html)

    defaults = parse_defaults_from_page(initial_html)
    LOGGER.debug("Defaults iniciales: %s", json.dumps(defaults, ensure_ascii=False, indent=2))
    defaults = _load_bootstrap_options(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )

    year_options = _load_options_for_field(
        session,
        "llenaAnios",
        [],
        "anioagric",
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    year_value = find_option_value(year_options, year, "year")
    defaults["anioagric"] = year_value
    defaults["tipo-reporte"] = FIXED_LABELS["tipo_reporte"]

    month_options = _load_options_for_field(
        session,
        "llenaMes",
        [year_value],
        "mesagric",
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    month_value = find_option_value(month_options, month, "month")
    month_label = next((option.label for option in month_options if option.value == month_value), month)
    defaults["mesagric"] = month_value

    ciclo_options = _load_options_for_field(
        session,
        "llenaCiclo",
        [],
        "cicloProd",
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    defaults["cicloProd"] = find_option_value(ciclo_options, FIXED_LABELS["ciclo"], "ciclo")

    modalidad_options = _load_options_for_field(
        session,
        "llenaModa",
        [],
        "modalidad",
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    defaults["modalidad"] = find_option_value(
        modalidad_options,
        FIXED_LABELS["modalidad"],
        "modalidad",
    )

    entidad_options = _load_options_for_field(
        session,
        "llenaEntidades",
        [],
        "entidad",
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    defaults["entidad"] = find_option_value(entidad_options, FIXED_LABELS["entidad"], "entidad")
    defaults["opcionDDRMpio"] = FIXED_LABELS["opcion_ddr_mpio"]

    for function_name, field_name in (
        ("llenaTipoAgric", "agric"),
        ("llenaTipoProd", "tiprod"),
        ("llenaTipoMerc", "timerc"),
    ):
        options = _load_options_for_field(
            session,
            function_name,
            [0],
            field_name,
            debug_dir=debug_dir,
            call_counter=call_counter,
        )
        defaults[field_name] = find_option_value(options, FIXED_LABELS[field_name], field_name)

    defaults = _load_location_options(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )

    crop_options = _load_options_for_field(
        session,
        "llenaCultivo",
        [
            year_value,
            defaults["entidad"],
            month_value,
            defaults["cicloProd"],
            defaults["distrito"],
            defaults["municipio"],
        ],
        "cultivo",
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    crop_value = find_option_value(crop_options, crop, "crop")
    defaults["cultivo"] = crop_value

    defaults = _load_crop_dependent_options(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    LOGGER.debug("Parámetros finales: %s", json.dumps(defaults, ensure_ascii=False, indent=2))

    submit_report(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    return session, month_value, month_label


def fetch_report_dataframe(
    year: str,
    month: str,
    crop: str,
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
) -> pd.DataFrame:
    session, month_value, month_label = prepare_report_session(
        year=year,
        month=month,
        crop=crop,
        debug=debug,
        debug_dir=debug_dir,
    )
    try:
        content = _fetch_report_content(session)
    finally:
        session.close()
    return _report_content_to_dataframe(
        content,
        year=year,
        month_value=month_value,
        month_label=month_label,
        crop=crop,
    )


def build_report(
    year: str,
    month: str,
    crop: str,
    output: Path,
    output_format: str,
    *,
    debug: bool,
    debug_dir: Path | None,
) -> None:
    session, month_value, month_label = prepare_report_session(
        year=year,
        month=month,
        crop=crop,
        debug=debug,
        debug_dir=debug_dir,
    )
    try:
        save_report(
            session,
            output,
            output_format,
            year=year,
            month_value=month_value,
            month_label=month_label,
            crop=crop,
        )
    finally:
        session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga reporte de Avance Agricola SIAP vía requests+xajax")
    parser.add_argument("--year", required=True, help="Año visible en el combo, por ejemplo 2026")
    parser.add_argument(
        "--month",
        required=True,
        help="Mes visible o valor del combo, por ejemplo Febrero o 2",
    )
    parser.add_argument("--crop", required=True, help="Cultivo visible, por ejemplo Aguacate")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta base de salida. Default: data/raw/avance_agricola/<cultivo>_<anio>_<mes>",
    )
    parser.add_argument(
        "--output-format",
        choices=("xls", "csv", "xlsx"),
        default="xlsx",
        help="Formato de salida. Por defecto: xlsx",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa logs DEBUG y guarda respuestas xajax en --debug-dir",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=Path("debug_avance_agricola"),
        help="Directorio para volcado de respuestas HTTP cuando --debug está activo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.debug)
    debug_dir = args.debug_dir if args.debug else None
    output = args.output or _default_output_path(args.year, args.month, args.crop)

    try:
        build_report(
            year=args.year,
            month=args.month,
            crop=args.crop,
            output=output,
            output_format=args.output_format,
            debug=args.debug,
            debug_dir=debug_dir,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Error en scraping de avance agricola: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
