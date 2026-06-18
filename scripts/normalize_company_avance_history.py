from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.analysis.common import normalize_key

MONTH_COLUMNS: list[tuple[str, int, str]] = [
    ("jan", 1, "Enero"),
    ("feb", 2, "Febrero"),
    ("mar", 3, "Marzo"),
    ("apr", 4, "Abril"),
    ("may", 5, "Mayo"),
    ("jun", 6, "Junio"),
    ("jul", 7, "Julio"),
    ("aug", 8, "Agosto"),
    ("sep", 9, "Septiembre"),
    ("oct", 10, "Octubre"),
    ("nov", 11, "Noviembre"),
    ("dec", 12, "Diciembre"),
]

REQUIRED_COLUMNS = {"tipo", "cultivo", "anio", "estados", *(column for column, _, _ in MONTH_COLUMNS)}

# Priority matters when more than one source label maps to the same canonical product.
CROP_LABEL_MAP: dict[str, tuple[str, str, int]] = {
    "aguacate": ("Aguacate", "AGUACATE", 0),
    "cebolla": ("Cebolla", "CEBOLLA", 0),
    "chile_verde": ("Chile verde", "CHILE VERDE", 0),
    "limon": ("Limón", "LIMON", 0),
    "mango": ("Mango", "MANGO", 0),
    "papa": ("Papa", "PAPA", 0),
    "platano": ("Plátano", "PLATANO", 0),
    "zanahoria": ("Zanahoria", "ZANAHORIA", 0),
    "maiz_grano": ("Elote", "MAIZ GRANO", 0),
    "tomate_rojo_jitomate": ("Tomate rojo", "TOMATE ROJO (JITOMATE)", 0),
    "tomate_rojo": ("Tomate rojo", "TOMATE ROJO", 1),
}

STATE_DISPLAY_MAP = {
    "aguascalientes": "Aguascalientes",
    "baja_california": "Baja California",
    "baja_california_sur": "Baja California Sur",
    "campeche": "Campeche",
    "chiapas": "Chiapas",
    "chihuahua": "Chihuahua",
    "ciudad_de_mexico": "Ciudad de México",
    "coahuila": "Coahuila",
    "colima": "Colima",
    "durango": "Durango",
    "guanajuato": "Guanajuato",
    "guerrero": "Guerrero",
    "hidalgo": "Hidalgo",
    "jalisco": "Jalisco",
    "mexico": "México",
    "michoacan": "Michoacán",
    "morelos": "Morelos",
    "nayarit": "Nayarit",
    "nuevo_leon": "Nuevo León",
    "oaxaca": "Oaxaca",
    "puebla": "Puebla",
    "queretaro": "Querétaro",
    "quintana_roo": "Quintana Roo",
    "san_luis_potosi": "San Luis Potosí",
    "sinaloa": "Sinaloa",
    "sonora": "Sonora",
    "tabasco": "Tabasco",
    "tamaulipas": "Tamaulipas",
    "tlaxcala": "Tlaxcala",
    "total": "Total",
    "veracruz": "Veracruz",
    "yucatan": "Yucatán",
    "zacatecas": "Zacatecas",
}

DROP_STATE_KEYS = {"", "estado"}


def trim_trailing_zero_suffix(values: list[Any]) -> list[Any]:
    last_positive = -1
    for index, value in enumerate(values):
        if pd.notna(value) and float(value) > 0:
            last_positive = index
    if last_positive == -1:
        return values
    trimmed = list(values)
    for index in range(last_positive + 1, len(trimmed)):
        value = trimmed[index]
        if pd.isna(value) or float(value) == 0:
            trimmed[index] = pd.NA
    return trimmed


def _display_state(value: Any) -> str:
    key = normalize_key(value)
    if key in DROP_STATE_KEYS:
        return ""
    return STATE_DISPLAY_MAP.get(key, str(value).strip().title())


def load_company_history(path: Path, years: set[int] | None = None) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Faltan columnas requeridas en {path}: {missing_text}")
    frame["anio"] = pd.to_numeric(frame["anio"], errors="coerce").astype("Int64")
    if years is not None:
        frame = frame.loc[frame["anio"].isin(sorted(years))].copy()
    frame["cultivo_key"] = frame["cultivo"].map(normalize_key)
    frame["estado"] = frame["estados"].map(_display_state)
    frame = frame.loc[frame["estado"].ne("")].copy()
    metadata = frame["cultivo_key"].map(CROP_LABEL_MAP)
    frame = frame.loc[metadata.notna()].copy()
    frame[["cultivo_canonico", "cultivo_original_estandar", "prioridad_cultivo"]] = pd.DataFrame(
        metadata.loc[frame.index].tolist(),
        index=frame.index,
    )

    for column, _, _ in MONTH_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Float64")

    month_only = [column for column, _, _ in MONTH_COLUMNS]
    trimmed_values = frame[month_only].apply(
        lambda row: pd.Series(trim_trailing_zero_suffix(row.tolist()), index=month_only),
        axis=1,
    )
    frame.loc[:, month_only] = trimmed_values.astype("Float64")
    return frame


def build_historical_avance_frame(path: Path, years: set[int] | None = None) -> pd.DataFrame:
    source = load_company_history(path, years=years)
    long_frames: list[pd.DataFrame] = []
    for column, month_number, month_name in MONTH_COLUMNS:
        chunk = source[
            [
                "tipo",
                "cultivo_canonico",
                "cultivo_original_estandar",
                "prioridad_cultivo",
                "anio",
                "estado",
                column,
            ]
        ].copy()
        chunk = chunk.rename(columns={column: "valor"})
        chunk["mes_consulta"] = month_number
        chunk["mes_consulta_nombre"] = month_name
        long_frames.append(chunk)

    long = pd.concat(long_frames, ignore_index=True)
    long = long.dropna(subset=["valor", "anio"]).copy()
    long["anio"] = long["anio"].astype(int)
    long = long.sort_values(
        [
            "cultivo_canonico",
            "estado",
            "anio",
            "mes_consulta",
            "tipo",
            "prioridad_cultivo",
        ]
    )
    long = long.drop_duplicates(
        ["cultivo_canonico", "estado", "anio", "mes_consulta", "tipo"],
        keep="first",
    )

    label_columns = ["cultivo_canonico", "estado", "anio", "mes_consulta", "mes_consulta_nombre"]
    label_frame = (
        long.sort_values("prioridad_cultivo")
        .drop_duplicates(label_columns, keep="first")[
            label_columns + ["cultivo_original_estandar"]
        ]
    )

    pivot = (
        long.pivot_table(
            index=[
                "cultivo_canonico",
                "estado",
                "anio",
                "mes_consulta",
                "mes_consulta_nombre",
            ],
            columns="tipo",
            values="valor",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    pivot = pivot.merge(label_frame, on=label_columns, how="left")

    if "SIEMBRA" not in pivot.columns:
        pivot["SIEMBRA"] = pd.NA
    if "COSECHA" not in pivot.columns:
        pivot["COSECHA"] = pd.NA

    pivot = pivot.rename(
        columns={
            "estado": "entidad_entidad",
            "cultivo_canonico": "cultivo_avance_agricola",
            "cultivo_original_estandar": "cultivo_avance_agricola_original",
            "anio": "anio_consulta",
            "SIEMBRA": "superficie_sembrada_ha",
            "COSECHA": "superficie_cosechada_ha",
        }
    )
    pivot["superficie_siniestrada_ha"] = pd.NA
    pivot["produccion_produccion"] = pd.NA
    pivot["rendimiento_udm_ha_rendimiento_udm_ha"] = pd.NA
    pivot["unidad_avance_agricola"] = "ha"
    pivot["situacion_corte"] = (
        "Historico interno empresarial al cierre de "
        + pivot["mes_consulta_nombre"]
        + " de "
        + pivot["anio_consulta"].astype(str)
    )
    pivot["nombre_fuente"] = "historico_empresa_siembra_cosecha"
    pivot = pivot.sort_values(
        ["cultivo_avance_agricola", "anio_consulta", "mes_consulta", "entidad_entidad"]
    ).reset_index(drop=True)
    return pivot[
        [
            "entidad_entidad",
            "superficie_sembrada_ha",
            "superficie_cosechada_ha",
            "superficie_siniestrada_ha",
            "produccion_produccion",
            "rendimiento_udm_ha_rendimiento_udm_ha",
            "cultivo_avance_agricola_original",
            "unidad_avance_agricola",
            "cultivo_avance_agricola",
            "anio_consulta",
            "mes_consulta",
            "mes_consulta_nombre",
            "situacion_corte",
            "nombre_fuente",
        ]
    ]


def write_historical_avance_outputs(frame: pd.DataFrame, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    total_rows = 0
    for (crop, year), group in frame.groupby(["cultivo_avance_agricola", "anio_consulta"], sort=True):
        export = group.reset_index(drop=True).copy()
        export.insert(0, "numero", range(1, len(export) + 1))
        crop_slug = normalize_key(crop)
        output_path = output_root / f"{crop_slug}_{int(year)}_historico_empresa.xlsx"
        export.to_excel(output_path, index=False, sheet_name="Sheet1")
        files.append(str(output_path))
        total_rows += len(export)
    summary = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "rows_written": total_rows,
        "files_written": len(files),
        "files": files,
    }
    (output_root / "batch_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convierte el CSV historico interno de siembras/cosechas en exportes XLSX compatibles "
            "con el layout usado por el nowcast de produccion."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/avance_agricola_batch/siembras_cosechas_202606171814.csv"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/raw/avance_agricola_batch/company_historical_avance"),
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=[2023, 2024],
        help=(
            "Anios agricolas objetivo a exportar. Por default solo 2023 y 2024 para sumar "
            "historia etiquetada sin sobrescribir el Avance oficial 2026."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    years = {int(year) for year in args.years}
    frame = build_historical_avance_frame(args.input, years=years)
    summary = write_historical_avance_outputs(frame, args.output_root)
    summary["input"] = str(args.input)
    summary["years_requested"] = sorted(years)
    summary["historical_rows"] = int(len(frame))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
