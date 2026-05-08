# AGENTS.md

## Misión del proyecto

Este repositorio existe para recolectar datos agroindustriales de múltiples fuentes públicas y comerciales en México y convertirlos en insumos de análisis con calidad de consultoría.

El código actual está orientado primero a extracción:

- La adquisición confiable de datos importa más que agregar modelado especulativo.
- Cada dataset debe conservar procedencia, parámetros de consulta y metadatos suficientes para auditar de dónde salió cada cifra.
- La meta de corto plazo es construir activos de datos repetibles y análisis operativos para una firma de consultoría agro.
- La meta de largo plazo puede incluir modelado, pronósticos, inteligencia de precios y reportes ejecutivos, pero los agentes no deben fingir que ese pipeline ya existe.

## Regla prioritaria de idioma

Toda la superficie pública del repositorio debe estar en español.

Esto incluye:

- Nombres de columnas exportadas.
- Nombres de archivos generados.
- Nombres de hojas de Excel y tablas visibles.
- Títulos, etiquetas y texto visible en notebooks o reportes.
- Documentación operativa y ejemplos dirigidos al usuario.

El inglés puede permanecer solo en variables internas, helpers, nombres privados de funciones o detalles de implementación que no formen parte de la salida pública.

Reglas operativas:

- Si un agente agrega una nueva salida pública, debe nombrarla en español desde el inicio.
- Si existe compatibilidad heredada en inglés, puede mantenerse como alias de lectura, pero no debe seguir emitiéndose como nombre oficial nuevo.
- Cuando cambie cualquier interfaz pública visible, el agente debe actualizar `README.md` y este `AGENTS.md` en el mismo cambio.

## Qué es hoy este repo

- Proyecto de extracción de datos en Python 3.12.
- Valor implementado principal: scrapers específicos por fuente más un orquestador diario.
- Fuentes principales hoy:
  - `SNIIM` para precios de frutas y hortalizas.
  - `SIAP Cierre Agricola` vía flujo HTTP/xajax legado.
  - `SIAP Cierre Agricola` con fallback en Playwright.
  - Scraping de búsqueda de productos frescos en `Walmart Mexico`.
  - Scraping de búsqueda de productos frescos en `Chedraui Mexico`.
- Las pruebas actuales se enfocan en parsing y orquestación diaria.
- `scikit-learn` y `xgboost` están instalados, pero todavía no existe un pipeline formal de modelado o pronóstico.

Los agentes deben tratar este repo como una base de adquisición y análisis de datos, no como una plataforma analítica terminada.

## Intención central del producto

Cuando trabajes en este repo, optimiza por estos resultados:

- Agregar fuentes confiables.
- Mejorar la resiliencia de extracción cuando cambien HTML o flujos.
- Estandarizar salidas para facilitar comparación entre fuentes.
- Hacer reproducible el análisis de consultoría.
- Mantener estructura suficiente para que después se puedan construir pronósticos, dashboards y reportes para clientes sin rehacer la ingestión.

## Mapa del repo

- `src/extract/sniim.py`: extractor SNIIM y helpers de exportación.
- `src/extract/cierre_agricola_requests.py`: implementación principal HTTP/xajax de SIAP Cierre Agricola.
- `src/extract/scraper_cierre_agricola_playwright.py`: fallback con navegador para SIAP cuando falle el flujo HTTP.
- `src/extract/walmart_produce_scraper.py`: scraper de Walmart y lógica de ranking de registros.
- `src/extract/chedraui_produce_scraper.py`: scraper de Chedraui y normalización de resultados de búsqueda.
- `src/extract/spreadsheet_localization.py`: aliases de columnas, nombres de hojas y nombres públicos en español.
- `scripts/run_daily_extracts.py`: orquestador principal de corridas diarias.
- `scripts/fetch_cierre_batch.py`: corrida en lote de exportes normalizados de Cierre Agricola para los productos canónicos configurados.
- `scripts/build_master_price_workbook.py`: construcción del libro maestro comparativo a partir de corridas diarias y exportes normalizados de Cierre Agricola.
- `scripts/run_daily_extracts_task.cmd`: wrapper para Windows Task Scheduler usando el virtualenv local.
- `config/products.xlsx`: workbook operativo de configuración para mapeos de productos y fuentes habilitadas.
- `notebooks/cuaderno_eda_precios.ipynb`: notebook base para graficar y explorar el libro maestro.
- `tests/`: pruebas unitarias y fixtures.
- `data/`: datos generados y corridas diarias.
- `debug_cierre_agricola/`: artefactos de depuración HTTP/xajax y referencias frontend como `funciones_cierre.js`.

## Comandos operativos

Ejecuta todo desde la raíz del repo.

Preparación del entorno:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Correr pruebas:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Correr el orquestador diario:

```powershell
python scripts/run_daily_extracts.py --config config/products.xlsx --output-root data/daily_runs
```

## Guía por fuente

### SNIIM

- `src/extract/sniim.py` usa el flujo real de formularios ASP.NET.
- Ejecuta el extractor desde la raíz como `python -m src.extract.sniim ...` para que resuelvan bien los imports del paquete.
- Conserva campos ocultos y validación de la página resultado; no simplifiques el flujo sin verificar que el sitio siga comportándose igual.
- Mantén metadatos de consulta en el `DataFrame` exportado para que los análisis sean auditables.
- Conserva la etiqueta de producto que aparece en la cabecera del reporte cuando exista, porque SNIIM puede mostrar nombres más específicos como `Aguacate Hass`.
- La robustez del parser importa porque los encabezados y codificaciones pueden ser inconsistentes.

### SIAP Cierre Agricola

- Prefiere `src/extract/cierre_agricola_requests.py` primero; es más rápido y más automatizable que scraping solo con navegador.
- Ejecuta el extractor HTTP desde la raíz como `python -m src.extract.cierre_agricola_requests ...`.
- Usa `python -m scripts.fetch_cierre_batch ...` cuando necesites una corrida por año y producto para alimentar el libro comparativo.
- Usa Playwright solo como fallback cuando el flujo HTTP/xajax cambie o ya no pueda reproducirse bien con `requests`.
- Cuando depures esta fuente, conserva el flujo con `--debug` y `--debug-dir`; los snapshots XML/HTML son valiosos cuando cambia el portal.
- Trata `debug_cierre_agricola/funciones_cierre.js` como ayuda de ingeniería inversa del flujo original del portal, no como código de runtime del scraper.
- Conserva `cierre_crop_label_raw` y `cierre_unit_label` en las salidas normalizadas para no perder contexto de unidad del PMR anual.
- Ten cuidado con el comportamiento dependiente de sesión; la descarga depende de que el flujo xajax haya creado el estado del reporte antes de llamar `reporte.php`.

### Walmart

- El scraper lee `__NEXT_DATA__` y rankea productos candidatos por cultivo configurado.
- Conserva la detección de página bloqueada. Un HTML silenciosamente malo es peor que un fallo explícito.
- La calidad del ranking importa porque el análisis de consultoría necesita el mejor precio representativo por cultivo, no cualquier resultado.

### Chedraui

- El scraper mezcla múltiples endpoints de búsqueda y deduplica por identidad normalizada de producto.
- Mantén el filtrado por término de búsqueda lo suficientemente estricto para evitar contaminación con productos no relacionados.
- Trata con cuidado la extracción de precio actual y precio anterior; la lógica promocional sí afecta el análisis downstream.

### Orquestador diario

- `scripts/run_daily_extracts.py` es hoy la entrada más parecida a producción.
- Está diseñado para tolerar fallas: una fuente o una fila pueden fallar sin matar toda la corrida.
- Conserva `resumen_corrida.json`, hojas de `metadatos` y reportes de falla por fuente.
- Si agregas una fuente nueva, intégrala de forma que siga habiendo éxito parcial y diagnósticos por fila y por fuente.

### Libro maestro comparativo

- `scripts/build_master_price_workbook.py` debe tratar `data/daily_runs/YYYY-MM-DD` como fuente de verdad para entradas diarias.
- Un flujo práctico de refresco es: primero correr el batch anual de Cierre Agricola y después reconstruir el libro maestro apuntando a ese `--cierre-root`.
- Mantén la salida comparativa lista para análisis en Excel: una hoja larga, una comparativa ancha y hojas de estadísticas y cobertura explícitas.
- No ocultes la ambigüedad de unidades en Cierre Agricola. Conserva y muestra la unidad del PMR anual en lugar de fingir comparabilidad directa con kg.

## Reglas de datos y salidas

- Trata las salidas generadas como desechables salvo que el usuario pida explícitamente que se versionen.
- `.gitignore` ya excluye `data/daily_runs/`, logs y salidas tabulares como `*.xlsx`, `*.xls` y `*.csv`.
- `config/products.xlsx` es operativo e importante, pero hoy está ignorado por git, así que no asumas que sus cambios se versionarán.
- Conserva columnas de procedencia y metadatos exportados siempre que sea posible.
- Prefiere cambios aditivos de esquema sobre renombres rompientes, salvo que actualices juntos consumidores downstream y documentación.

## Reglas de pruebas y validación

- Prefiere pruebas unitarias de parser por encima de pruebas live-site para desarrollo normal.
- Usa fixtures y mocks para fuentes externas siempre que sea posible.
- Si cambias un parser, agrega o actualiza una prueba enfocada en `tests/`.
- Si cambias columnas del workbook, nombres de hojas, nombres de archivos de salida o estructura de JSONs resumen, valida `scripts/run_daily_extracts.py` y actualiza pruebas.
- Para investigar roturas de fuente, captura la respuesta exacta o el artefacto de debug antes de parchear heurísticas.

## Reglas de colaboración para agentes

- Mantén confiable la capa de extracción antes de agregar nuevas capas analíticas.
- Favorece funciones claras y específicas por fuente sobre abstracciones genéricas grandes que oculten el comportamiento real del scraper.
- No elimines capacidad de depuración en fuentes frágiles solo para que el código se vea más limpio.
- Mantén alineadas las guías operativas y documentación con los comandos y rutas reales del repo.
- Si una conducta vale la pena documentarse, documéntala de inmediato y no la dejes como conocimiento tribal escondido en el código.

## Regla de mantenimiento de documentación

Cada vez que un agente cree o modifique algo que valga la pena mencionar, debe actualizar `README.md` y este `AGENTS.md` en el mismo cambio cuando la documentación pueda quedar desfasada.

Ejemplos que normalmente requieren actualización de docs:

- Nuevas integraciones de fuentes.
- Nuevos scripts o entrypoints.
- Cambios en columnas del workbook o nombres de hojas.
- Cambios en archivos de salida, directorios de salida o JSONs resumen.
- Cambios en scheduling o comandos operativos.
- Limitaciones importantes, modos de falla o flujos de depuración.

## Siguientes áreas de alto valor

Trabajo de alto valor en este repo normalmente se parece a esto:

- Agregar un dataset intermedio normalizado que alinee campos entre retailers y fuentes públicas.
- Agregar checks de calidad para precios faltantes, outliers y desajustes sospechosos de unidad.
- Construir scripts reutilizables para spreads, comparaciones entre fuentes, estacionalidad y brechas PMR vs retail.
- Versionar salidas listas para análisis por separado de los extractos crudos.
- Agregar un pipeline formal de transformación y forecasting cuando la calidad de ingestión ya sea suficientemente estable.

Los agentes deben ser proactivos al sugerir o implementar estos pasos cuando apoyen claramente el caso de uso de consultoría.
