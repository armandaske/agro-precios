"""Scraper HTTP (sin navegador) para Cierre Agrícola SIAP.

Flujo implementado:
1) Abre la página principal para establecer cookies de sesión.
2) Reproduce llamadas xajax para poblar opciones y ejecutar `reporte`.
3) Descarga el Excel desde `Clases/reporte.php` con la misma sesión.

Solo expone dos entradas de usuario:
- year
- crop
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://nube.agricultura.gob.mx/cierre_agricola/"
REPORTE_XLS_URL = BASE_URL + "Clases/reporte.php"
DEFAULT_TIMEOUT = 45

LOGGER = logging.getLogger("cierre_agricola_http")


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
    # Formato típico de xajax (0.5+): xajax, xajaxr y xajaxargs[]
    payload: dict[str, Any] = {
        "xajax": function_name,
        "xajaxr": f"{time.time():.6f}",
        "xajaxargs[]": [str(arg) for arg in args],
    }
    return payload


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

    commands = parse_xajax_commands(text)
    if not commands:
        LOGGER.warning(
            "xajax %s regresó sin comandos parseables (revisa debug XML).", function_name
        )

    return XajaxResult(response_text=text, commands=commands)


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
        # Respuesta no-XML o XML parcial, intentamos extraer CDATA por regex para depurar.
        cdata_blocks = re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml_text, flags=re.DOTALL)
        for block in cdata_blocks:
            commands.append({"n": "unknown", "t": "", "p": "", "data": block})
        return commands


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _extract_options_from_html(html: str) -> list[Option]:
    soup = BeautifulSoup(html, "html.parser")
    options: list[Option] = []
    for opt in soup.select("option"):
        val = (opt.get("value") or "").strip()
        label = opt.get_text(" ", strip=True)
        if not label:
            continue
        options.append(Option(value=val, label=label, selected=opt.has_attr("selected")))
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

    # Inputs esperados por reporte(). Si no existen, usan vacío.
    keys = [
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
        "noseg",
    ]

    for key in keys:
        tag = soup.find(id=key)
        if tag is None:
            # En algunas variantes del markup, el atributo `name` se usa
            # y el `id` no coincide exactamente.
            tag = soup.find(attrs={"name": key})
        if tag is None:
            defaults[key] = ""
            continue

        if tag.name == "select":
            selected = tag.find("option", selected=True)
            if selected is None:
                selected = tag.find("option")
            defaults[key] = (selected.get("value") if selected else "") or ""
        else:
            defaults[key] = (tag.get("value") or "").strip()

    return defaults


def _pick_default_from_options(
    options: list[Option],
    *,
    prefer_non_empty: bool = True,
    allow_blank_when_multiselect: bool = False,
    prefer_last_when_multiselect: bool = False,
) -> str:
    if not options:
        return ""

    selected_values = [opt.value for opt in options if opt.selected]
    if allow_blank_when_multiselect and len(selected_values) > 1:
        # En varios combos del sitio (p.ej. ciclo/modalidad) el backend marca
        # todos los elementos como selected. Tomar solo el primero sobrerrestringe
        # el reporte y puede dejar la sesión sin `Tabla`.
        # Dejamos cadena vacía para representar "todos" (comportamiento observado
        # previamente en el frontend cuando no hay un único valor seleccionado).
        return ""
    if prefer_last_when_multiselect and len(selected_values) > 1:
        for value in reversed(selected_values):
            if value.strip() != "":
                return value
        return selected_values[-1]

    if selected_values:
        if prefer_non_empty:
            for value in selected_values:
                if value.strip() != "":
                    return value
        return selected_values[0]

    if prefer_non_empty:
        for option in options:
            if option.value.strip() != "":
                return option.value
    return options[0].value


def _update_state_from_innerhtml_commands(
    state: dict[str, str],
    commands: list[dict[str, Any]],
    targets: dict[str, set[str]],
) -> None:
    multiselect_like_fields = {"cicloProd", "modalidad"}
    for field_name, target_ids in targets.items():
        options = extract_options_from_commands(commands, target_ids)
        if options:
            state[field_name] = _pick_default_from_options(
                options,
                prefer_non_empty=True,
                # En la UI observada, ciclo/modalidad tienen un valor por defecto
                # concreto (p.ej. "Cíclicos - Perennes"), aunque backend marque
                # múltiples opciones como selected en el HTML devuelto.
                prefer_last_when_multiselect=field_name in multiselect_like_fields,
            )


def _update_state_from_js_commands(
    state: dict[str, str],
    commands: list[dict[str, Any]],
    id_to_field: dict[str, str],
) -> None:
    # Patrones frecuentes en respuestas xajax con instrucciones JS.
    patterns = [
        re.compile(r"""\$\('#(?P<id>[A-Za-z0-9_-]+)'\)\.val\('(?P<val>[^']*)'\)"""),
        re.compile(
            r"""document\.getElementById\('(?P<id>[A-Za-z0-9_-]+)'\)\.value\s*=\s*'(?P<val>[^']*)'"""
        ),
    ]

    for cmd in commands:
        if (cmd.get("n") or "") != "js":
            continue
        code = cmd.get("data", "")
        for pattern in patterns:
            for match in pattern.finditer(code):
                dom_id = match.group("id")
                value = match.group("val")
                field_name = id_to_field.get(dom_id)
                if field_name is not None:
                    state[field_name] = value


def _coerce_missing_report_values(state: dict[str, str]) -> None:
    # En el backend PHP del portal, muchos combos "Todos" se representan
    # como "0". Si se envían vacíos, el reporte puede no construir la
    # variable de sesión necesaria para reporte.php (Undefined index: Tabla).
    fallback_zero_fields = [
        "entidad",
        "distrito",
        "municipio",
        "opcionDDRMpio",
        "agric",
        "tiprod",
        "timerc",
        "noseg",
    ]
    for field in fallback_zero_fields:
        if state.get(field, "") == "":
            state[field] = "0"


def find_option_value(options: list[Option], wanted_label: str, field_name: str) -> str:
    wanted_norm = _normalize_text(wanted_label)

    exact = [opt for opt in options if _normalize_text(opt.label) == wanted_norm]
    if exact:
        return exact[0].value

    contains = [opt for opt in options if wanted_norm in _normalize_text(opt.label)]
    if len(contains) == 1:
        return contains[0].value

    sample = ", ".join(f"{o.label}({o.value})" for o in options[:10])
    raise ValueError(
        f"No se encontró coincidencia única para {field_name}='{wanted_label}'. "
        f"Opciones ejemplo: {sample}"
    )


def get_year_options(
    session: requests.Session,
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> list[Option]:
    call_counter[0] += 1
    result = xajax_call(
        session,
        "llenaAnios",
        [],
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    options = extract_options_from_commands(result.commands, {"anioagric"})
    if not options:
        raise RuntimeError("No fue posible extraer opciones de año desde xajax_llenaAnios")
    return options


def get_crop_options(
    session: requests.Session,
    year_value: str,
    entidad: str,
    noseg: str,
    *,
    debug_dir: Path | None,
    call_counter: list[int],
) -> list[Option]:
    call_counter[0] += 1
    result = xajax_call(
        session,
        "llenaCultivo",
        [year_value, entidad, noseg],
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    options = extract_options_from_commands(result.commands, {"cultivo"})
    if not options:
        raise RuntimeError("No fue posible extraer opciones de cultivo desde xajax_llenaCultivo")
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
        "distrito": {"distrito"},
        "municipio": {"municipio"},
        "unidMed": {"unidMed"},
        "variedad": {"variedad"},
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
        try:
            result = xajax_call(
                session,
                function_name,
                args,
                debug_dir=debug_dir,
                call_index=call_counter[0],
            )
            _update_state_from_innerhtml_commands(state, result.commands, target_map)
            _update_state_from_js_commands(state, result.commands, id_to_field)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Bootstrap xajax %s falló o no aplicó: %s", function_name, exc)

    if state.get("entidad", "") == "":
        state["entidad"] = "0"
    if state.get("opcionDDRMpio", "") == "":
        state["opcionDDRMpio"] = "2"
    for field in ("agric", "tiprod", "timerc"):
        if state.get(field, "") == "":
            state[field] = "0"
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
        ("llenaDistrito", [state.get("entidad", "0")]),
        ("cargaMuni", [state.get("entidad", "0"), 0]),
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

    for field in ("distrito", "municipio"):
        if state.get(field, "") == "":
            state[field] = "0"
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

    dependent_calls: list[tuple[str, list[str | int]]] = [
        ("llenaUnidMed", [state["cultivo"]]),
    ]
    for function_name, args in dependent_calls:
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

    if state.get("unidMed", "") == "":
        state["unidMed"] = "0"

    call_counter[0] += 1
    result = xajax_call(
        session,
        "llenaVariedad",
        [state["cultivo"], state["unidMed"]],
        debug_dir=debug_dir,
        call_index=call_counter[0],
    )
    _update_state_from_innerhtml_commands(state, result.commands, target_map)
    _update_state_from_js_commands(state, result.commands, id_to_field)

    if state.get("variedad", "") == "":
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
        "noseg",
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
    # Confirmación mínima: suele actualizar un div/tabla con resultado.
    if not result.commands:
        raise RuntimeError("xajax_reporte no devolvió comandos; no se puede asegurar generación de Excel")


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
    LOGGER.info("Descargando Excel: %s", REPORTE_XLS_URL)
    response = session.get(REPORTE_XLS_URL, timeout=DEFAULT_TIMEOUT)
    ensure_ok_response(response, "Descarga de reporte.php")

    content_type = (response.headers.get("Content-Type") or "").lower()
    content = response.content

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

    excel_hint = any(
        marker in content_type
        for marker in (
            "application/vnd.ms-excel",
            "application/octet-stream",
            "application/vnd.openxmlformats-officedocument",
        )
    )
    if not excel_hint:
        LOGGER.warning("Content-Type no típico de Excel: %s", content_type)

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
    best_table = best_table.dropna(how="all").reset_index(drop=True)
    return best_table


def _write_html_xls(df: pd.DataFrame, output_path: Path) -> None:
    html = df.to_html(index=False, na_rep="", border=1)
    output_path.write_text(html, encoding="utf-8")


def save_report(session: requests.Session, output_path: Path, output_format: str) -> Path:
    resolved_output = _resolve_output_path(output_path, output_format)
    content = _fetch_report_content(session)
    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "xls":
        resolved_output.write_bytes(content)
        LOGGER.info("Archivo guardado: %s (%s bytes)", resolved_output, len(content))
        return resolved_output

    report_df = _html_report_to_dataframe(content)
    if output_format == "csv":
        report_df.to_csv(resolved_output, index=False, encoding="utf-8-sig")
        LOGGER.info("CSV guardado: %s (%s filas)", resolved_output, len(report_df))
    elif output_format == "xlsx":
        report_df.to_excel(resolved_output, index=False, engine="openpyxl")
        LOGGER.info("XLSX guardado: %s (%s filas)", resolved_output, len(report_df))
    else:
        raise ValueError(f"Formato de salida no soportado: {output_format}")
    return resolved_output


def prepare_report_session(
    year: str,
    crop: str,
    *,
    debug: bool,
    debug_dir: Path | None,
) -> requests.Session:
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

    # Replica la inicialización observada en JS.
    call_counter[0] += 1
    init_result = xajax_call(session, "reporte_inicio", [], debug_dir=debug_dir, call_index=call_counter[0])
    _update_state_from_js_commands(defaults, init_result.commands, {key: key for key in defaults})

    if defaults.get("entidad", "") == "":
        LOGGER.warning("No se detectó entidad por defecto; usando valor nacional")

    defaults = _load_bootstrap_options(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )

    year_options = get_year_options(session, debug_dir=debug_dir, call_counter=call_counter)
    year_value = find_option_value(year_options, year, "year")
    LOGGER.info("Año seleccionado: %s -> value=%s", year, year_value)
    defaults["anioagric"] = year_value

    defaults = _load_location_options(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )

    crop_options = get_crop_options(
        session,
        year_value,
        defaults.get("entidad", "0"),
        defaults.get("noseg", ""),
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    crop_value = find_option_value(crop_options, crop, "crop")
    LOGGER.info("Cultivo seleccionado: %s -> value=%s", crop, crop_value)
    defaults["cultivo"] = crop_value

    report_params = _load_crop_dependent_options(
        session,
        defaults,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    LOGGER.debug("Parámetros finales para xajax_reporte: %s", json.dumps(report_params, ensure_ascii=False))

    submit_report(
        session,
        report_params,
        debug_dir=debug_dir,
        call_counter=call_counter,
    )
    return session


def fetch_report_dataframe(
    year: str,
    crop: str,
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
) -> pd.DataFrame:
    session = prepare_report_session(year=year, crop=crop, debug=debug, debug_dir=debug_dir)
    try:
        content = _fetch_report_content(session)
    finally:
        session.close()
    return _html_report_to_dataframe(content)


def build_report(
    year: str,
    crop: str,
    output: Path,
    output_format: str,
    *,
    debug: bool,
    debug_dir: Path | None,
) -> None:
    session = prepare_report_session(year=year, crop=crop, debug=debug, debug_dir=debug_dir)
    try:
        save_report(session, output, output_format)
    finally:
        session.close()



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga reporte de Cierre Agrícola SIAP vía requests+xajax")
    parser.add_argument("--year", required=True, help="Año visible en el combo (ej. 2024)")
    parser.add_argument("--crop", required=True, help="Cultivo visible (ej. Aguacate)")
    parser.add_argument("--output", required=True, type=Path, help="Ruta base de salida")
    parser.add_argument(
        "--output-format",
        choices=("xls", "csv", "xlsx"),
        default="xls",
        help="Formato de salida. Por defecto: xls",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa logs DEBUG y guarda respuestas xajax en --debug-dir",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=Path("debug_cierre_agricola"),
        help="Directorio para volcado de respuestas HTTP cuando --debug está activo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.debug)

    debug_dir = args.debug_dir if args.debug else None

    try:
        build_report(
            year=args.year,
            crop=args.crop,
            output=args.output,
            output_format=args.output_format,
            debug=args.debug,
            debug_dir=debug_dir,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Error en scraping de cierre agrícola: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
