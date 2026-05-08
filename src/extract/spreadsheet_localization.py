from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

PRODUCT_SHEET_NAME = "productos"
PRODUCT_SHEET_NAME_ALIASES = ("productos", "products")
INSTRUCTIONS_SHEET_NAME = "instrucciones"

ARCHIVO_RESUMEN_CORRIDA = "resumen_corrida.json"
ARCHIVO_RESUMEN_CORRIDA_ALIASES = (ARCHIVO_RESUMEN_CORRIDA, "run_summary.json")
ARCHIVO_INSTANTANEA_PRODUCTOS = "instantanea_productos.xlsx"
ARCHIVO_INSTANTANEA_PRODUCTOS_ALIASES = (ARCHIVO_INSTANTANEA_PRODUCTOS, "products_snapshot.xlsx")
ARCHIVO_RESUMEN_LOTE_CIERRE = "resumen_lote.json"
ARCHIVO_RESUMEN_LOTE_CIERRE_ALIASES = (ARCHIVO_RESUMEN_LOTE_CIERRE, "batch_summary.json")
ARCHIVO_LIBRO_MAESTRO_PRECIOS = "libro_maestro_precios.xlsx"
ARCHIVO_LIBRO_MAESTRO_PRECIOS_ALIASES = (ARCHIVO_LIBRO_MAESTRO_PRECIOS, "master_price_workbook.xlsx")
ARCHIVO_CUADERNO_EDA_PRECIOS = "cuaderno_eda_precios.ipynb"
ARCHIVO_CUADERNO_EDA_PRECIOS_ALIASES = (ARCHIVO_CUADERNO_EDA_PRECIOS, "master_price_eda.ipynb")

CONFIG_COLUMN_ALIASES = {
    "activo": "active",
    "active": "active",
    "producto_canonico": "canonical_product",
    "canonical_product": "canonical_product",
    "walmart_habilitado": "walmart_enabled",
    "walmart_enabled": "walmart_enabled",
    "terminos_busqueda_walmart": "walmart_search_terms",
    "walmart_search_terms": "walmart_search_terms",
    "chedraui_habilitado": "chedraui_enabled",
    "chedraui_enabled": "chedraui_enabled",
    "terminos_busqueda_chedraui": "chedraui_search_terms",
    "chedraui_search_terms": "chedraui_search_terms",
    "sniim_habilitado": "sniim_enabled",
    "sniim_enabled": "sniim_enabled",
    "sniim_id_producto": "sniim_producto_id",
    "sniim_producto_id": "sniim_producto_id",
    "sniim_id_origen": "sniim_origen_id",
    "sniim_origen_id": "sniim_origen_id",
    "sniim_id_destino": "sniim_destino_id",
    "sniim_destino_id": "sniim_destino_id",
    "sniim_id_precios_por": "sniim_precios_por_id",
    "sniim_precios_por_id": "sniim_precios_por_id",
    "cierre_agricola_habilitado": "cierre_enabled",
    "cierre_enabled": "cierre_enabled",
    "cultivo_cierre_agricola": "cierre_crop_name",
    "cierre_crop_name": "cierre_crop_name",
}

CONFIG_EXPORT_COLUMN_MAP = {
    "active": "activo",
    "canonical_product": "producto_canonico",
    "walmart_enabled": "walmart_habilitado",
    "walmart_search_terms": "terminos_busqueda_walmart",
    "chedraui_enabled": "chedraui_habilitado",
    "chedraui_search_terms": "terminos_busqueda_chedraui",
    "sniim_enabled": "sniim_habilitado",
    "sniim_producto_id": "sniim_id_producto",
    "sniim_origen_id": "sniim_id_origen",
    "sniim_destino_id": "sniim_id_destino",
    "sniim_precios_por_id": "sniim_id_precios_por",
    "cierre_enabled": "cierre_agricola_habilitado",
    "cierre_crop_name": "cultivo_cierre_agricola",
}

INSTRUCTIONS_EXPORT_COLUMN_MAP = {
    "field": "campo",
    "description": "descripcion",
}

WALMART_EXPORT_COLUMN_MAP = {
    "scraped_at_utc": "fecha_extraccion_utc",
    "source": "fuente",
    "source_page": "pagina_fuente",
    "source_query": "termino_busqueda",
    "product_raw": "producto_original",
    "product_canonical": "producto_canonico",
    "product_inferred": "producto_inferido",
    "price_mxn": "precio_mxn",
    "old_price_mxn": "precio_anterior_mxn",
    "promo_flag": "esta_en_promocion",
    "unit_raw": "unidad_detectada",
    "estimated_price_per_kg_mxn": "precio_estimado_por_kg_mxn",
    "presentation_weight_kg": "peso_presentacion_kg",
    "sales_unit_type": "tipo_unidad_venta",
    "average_weight_kg": "peso_promedio_kg",
    "brand_raw": "marca_original",
    "category_path": "ruta_categoria",
    "fresh_produce_flag": "es_producto_fresco",
}

CHEDRAUI_EXPORT_COLUMN_MAP = {
    "scraped_at_utc": "fecha_extraccion_utc",
    "source": "fuente",
    "source_page": "pagina_fuente",
    "source_query": "termino_busqueda",
    "product_raw": "producto_original",
    "product_canonical": "producto_canonico",
    "product_inferred": "producto_inferido",
    "price_mxn": "precio_mxn",
    "old_price_mxn": "precio_anterior_mxn",
    "promo_flag": "esta_en_promocion",
    "unit_raw": "unidad_detectada",
    "estimated_price_per_kg_mxn": "precio_estimado_por_kg_mxn",
    "presentation_weight_kg": "peso_presentacion_kg",
    "brand_raw": "marca_original",
    "category_path": "ruta_categoria",
    "fresh_produce_flag": "es_producto_fresco",
}

SNIIM_EXPORT_COLUMN_MAP = {
    "fecha": "fecha",
    "producto": "producto",
    "producto_nombre_sitio": "producto_sniim",
    "presentacion": "presentacion",
    "origen": "origen",
    "destino": "destino",
    "precio_minimo": "precio_minimo",
    "precio_maximo": "precio_maximo",
    "precio_frecuente": "precio_frecuente",
    "obs": "observaciones",
    "fecha_inicio_query": "fecha_inicio_consulta",
    "fecha_final_query": "fecha_fin_consulta",
    "producto_id": "id_producto",
    "origen_id": "id_origen",
    "destino_id": "id_destino",
    "origen_query": "origen_consulta",
    "destino_query": "destino_consulta",
    "precios_por_id": "id_precios_por",
    "registros_por_pagina": "registros_por_pagina",
    "fuente": "fuente",
    "fecha_extraccion": "fecha_extraccion",
}

CIERRE_EXPORT_COLUMN_MAP = {
    "numero": "numero",
    "entidad": "entidad",
    "superficie_sembrada_ha": "superficie_sembrada_ha",
    "superficie_cosechada_ha": "superficie_cosechada_ha",
    "superficie_siniestrada_ha": "superficie_siniestrada_ha",
    "produccion": "produccion",
    "rendimiento_udm_ha": "rendimiento_udm_ha",
    "pmr_mxn_udm": "pmr_mxn_udm",
    "valor_produccion_miles_pesos": "valor_produccion_miles_pesos",
    "cierre_crop_label_raw": "cultivo_cierre_agricola_original",
    "cierre_unit_label": "unidad_cierre_agricola",
    "cierre_crop_name": "cultivo_cierre_agricola",
    "query_year": "anio_consulta",
    "source_name": "nombre_fuente",
}

DAILY_FAILURE_COLUMN_MAP = {
    "row_number": "numero_fila",
    "canonical_product": "producto_canonico",
    "source_name": "nombre_fuente",
    "identifier": "identificador",
    "error": "error",
}

DAILY_META_COLUMN_MAP = {
    "source_name": "nombre_fuente",
    "run_date": "fecha_corrida",
    "config_path": "ruta_configuracion",
    "rows_attempted": "filas_intentadas",
    "rows_succeeded": "filas_exitosas",
    "rows_failed": "filas_con_error",
    "query_start_date": "fecha_inicio_consulta",
    "query_end_date": "fecha_fin_consulta",
    "query_year": "anio_consulta",
}

DAILY_SHEET_NAMES = {
    "data": "datos",
    "failures": "errores",
    "meta": "metadatos",
}

MASTER_WORKBOOK_SHEET_NAMES = {
    "panel_diario_largo": "panel_diario_largo",
    "comparativo_diario_ancho": "comparativo_diario_ancho",
    "estadisticas_diarias_sniim": "estadisticas_diarias_sniim",
    "estadisticas_anuales_cierre": "estadisticas_anuales_cierre",
    "cobertura": "cobertura",
}

MASTER_WORKBOOK_SHEET_ALIASES = {
    "panel_diario_largo": ("panel_diario_largo", "panel_daily_long"),
    "comparativo_diario_ancho": ("comparativo_diario_ancho", "compare_daily_wide"),
    "estadisticas_diarias_sniim": ("estadisticas_diarias_sniim", "sniim_daily_stats"),
    "estadisticas_anuales_cierre": ("estadisticas_anuales_cierre", "cierre_annual_stats"),
    "cobertura": ("cobertura", "coverage"),
}

DAILY_SOURCE_COLUMN_MAPS = {
    "walmart": {
        **WALMART_EXPORT_COLUMN_MAP,
        "run_date": "fecha_corrida",
        "canonical_product": "producto_canonico",
        "source_name": "nombre_fuente",
        "search_terms_used": "terminos_busqueda_utilizados",
    },
    "sniim": {
        **SNIIM_EXPORT_COLUMN_MAP,
        "run_date": "fecha_corrida",
        "canonical_product": "producto_canonico",
        "source_name": "nombre_fuente",
        "query_start_date": "fecha_inicio_consulta",
        "query_end_date": "fecha_fin_consulta",
    },
    "chedraui": {
        **CHEDRAUI_EXPORT_COLUMN_MAP,
        "run_date": "fecha_corrida",
        "canonical_product": "producto_canonico",
        "source_name": "nombre_fuente",
        "search_terms_used": "terminos_busqueda_utilizados",
    },
    "cierre_agricola": {
        **CIERRE_EXPORT_COLUMN_MAP,
        "run_date": "fecha_corrida",
        "canonical_product": "producto_canonico",
    },
}


def rename_columns(df: pd.DataFrame, column_map: Mapping[str, str]) -> pd.DataFrame:
    renamed = df.copy()
    renamed.columns = [column_map.get(str(column), str(column)) for column in renamed.columns]
    return renamed


def rename_mapping_keys(data: Mapping[str, object], key_map: Mapping[str, str]) -> dict[str, object]:
    return {key_map.get(str(key), str(key)): value for key, value in data.items()}
