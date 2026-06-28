# Agro precios

POC para extraer y preparar datos de precios agroalimentarios en Mexico.

El repositorio combina una capa de extraccion con tres pipelines analiticos iniciales: riesgo hidrico, nowcast de produccion y alerta temprana de precios. Los modelos usan validacion temporal y solo se marcan como operativos cuando superan sus baselines.

## Guia para agentes y mantenimiento de docs

- Revisa `AGENTS.md` antes de hacer cambios importantes; ahi vive la guia operativa especifica del repo para agentes Codex.
- Cada vez que un agente cree o modifique algo que valga la pena documentar, debe actualizar `README.md` y `AGENTS.md` en el mismo cambio para evitar que las instrucciones queden desfasadas.
- Usa [COMMANDS.md](COMMANDS.md) como referencia rapida de comandos para los extractores, batch runners, workbook maestro y scheduler.
- Usa [ANALYSIS_GUIDE.md](ANALYSIS_GUIDE.md) para una explicacion detallada de cada pipeline, sus salidas, caveats y limites operativos.
- Todo texto orientado al usuario debe quedar en espanol por defecto: titulos, etiquetas, graficas, nombres de columnas, nombres de hojas y salidas visibles para analisis o consumo de negocio.

## Estado actual del repo

Implementado:

- Extraccion de precios de frutas y hortalizas desde SNIIM via `requests`.
- Descarga de reportes de Cierre Agricola SIAP via flujo HTTP/xajax.
- Descarga de reportes de Avance Agricola SIAP via flujo HTTP/xajax.
- Alternativa con Playwright para Cierre Agricola cuando el flujo HTTP no sea suficiente.
- Scraper HTTP para Presas Agricolas con consultas historicas por anio, mes y decena.
- Scraper de precios de productos frescos de Walmart Mexico.
- Scraper de precios de productos frescos de Chedraui Mexico.
- Tests unitarios para parsing de SNIIM, Presas Agricolas, Walmart y Chedraui.

Analitica implementada:

- Dataset por presa y decena, backtesting a 30, 60 y 90 dias, alertas de umbral y mapa HTML.
- Backfill anual reproducible de presas para reconstruir el historico nacional por decena con el mismo extractor HTTP.
- Dataset por cultivo, estado y corte mensual para nowcast de produccion, con comparativo explicito vs anio anterior o promedio 5 anios cuando exista.
- Dataset diario por producto y mercado, forecast a 7, 14 y 28 dias y anomalias de margen retail-mayoreo.
- Descarga opcional de clima NASA POWER.
- Capa opcional de precios internacionales publicos sin API keys: World Bank Pink Sheet, FRED USD/MXN y archivos publicos descargados de USDA AMS o IMF.
- Orquestador `scripts/run_analysis_pipeline.py` para reconstruir el workbook maestro y ejecutar los tres analisis.
- Wrapper operativo `scripts/fetch_presas_decena_snapshot.py` para descargar el corte nacional de presas por decena con config generada, salida timestamped e idempotencia por periodo.

Limitacion actual:

- Los exportes oficiales de Avance Agricola disponibles en el repo siguen concentrados en 2026. El script `scripts/normalize_company_avance_history.py` puede sumar historia 2023-2024 desde un CSV interno de siembras/cosechas, pero esa capa historica solo aporta superficies acumuladas y no reemplaza columnas como `produccion`, `rendimiento` o `superficie_siniestrada`.

## Estructura relevante

- `src/extract/sniim.py`: extractor SNIIM y export a CSV/XLSX.
- `src/extract/cierre_agricola_requests.py`: scraper HTTP para Cierre Agricola.
- `src/extract/avance_agricola_requests.py`: scraper HTTP para Avance Agricola.
- `src/extract/scraper_cierre_agricola_playwright.py`: alternativa con navegador.
- `src/extract/presas_agricolas.py`: scraper HTTP del portal de Presas Agricolas y generador del workbook de consultas.
- `src/extract/walmart_produce_scraper.py`: scraper de frutas y verduras en Walmart.
- `src/extract/chedraui_produce_scraper.py`: scraper de frutas y verduras en Chedraui.
- `scripts/run_daily_extracts.py`: orquestador diario para las 4 fuentes.
- `scripts/fetch_cierre_batch.py`: descarga en lote exportes normalizados de Cierre Agricola para los productos canonicos configurados.
- `scripts/fetch_avance_batch.py`: descarga en lote exportes normalizados de Avance Agricola para los productos canonicos configurados.
- `scripts/normalize_company_avance_history.py`: convierte el CSV historico interno de siembras/cosechas en exportes XLSX compatibles con el layout consumido por el nowcast de produccion.
- `scripts/build_master_price_workbook.py`: constructor del workbook maestro comparativo para SNIIM, Walmart, Chedraui, Avance Agricola y Cierre Agricola secundario.
- `scripts/run_water_risk_model.py`: monitor predictivo de riesgo hidrico.
- `scripts/fetch_presas_historical_backfill.py`: backfill anual del corte nacional de presas para reforzar entrenamiento historico.
- `scripts/run_production_nowcast.py`: nowcast de produccion y rendimiento.
- `scripts/run_price_shock_model.py`: alerta temprana de choques de precios.
- `scripts/run_analysis_pipeline.py`: ejecucion integrada de los tres proyectos.
- `scripts/fetch_nasa_power_weather.py`: descarga clima diario por coordenada y agrega por decena.
- `scripts/fetch_public_international_prices.py`: descarga fuentes internacionales publicas que no requieren token.
- `scripts/build_international_price_features.py`: normaliza proxies internacionales y genera features auditables.
- `scripts/fetch_presas_decena_snapshot.py`: wrapper operativo para descargar y almacenar un corte nacional por decena usando el extractor existente de Presas Agricolas.
- `src/analysis/`: feature engineering, validacion temporal, seleccion de baselines, modelos y reportes.
- `config/products.xlsx`: workbook editable por el usuario con la configuracion de productos.
- `config/presas_agricolas.xlsx`: workbook editable por el usuario con consultas de presas por anio, mes, decena e `id_conagua`.
- `notebooks/master_price_eda.ipynb`: notebook base para graficar y explorar el workbook maestro.
- `tests/`: pruebas unitarias.
- `data/raw/sniim/`: salidas generadas por el extractor SNIIM.
- `debug_cierre_agricola/`: respuestas de depuracion del scraper de Cierre Agricola y archivos de referencia del frontend SIAP, como `funciones_cierre.js`.

## Requisitos

- Python 3.12 recomendado.
- Python 3.13 no esta validado con los pins actuales de `requirements.txt`.
- Crear y activar un entorno virtual.
- Instalar dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si vas a usar el scraper con Playwright, instala tambien el navegador:

```powershell
playwright install chromium
```

## Como correr los scrapers manualmente

Todos los comandos siguientes se ejecutan desde la raiz del repo.

Default operativo:

- Usa siempre el interprete del repo: `.venv\Scripts\python.exe`.
- Si activaste el entorno con `.\.venv\Scripts\Activate.ps1`, `python` ya apuntara al `.venv`, pero para automatizacion y agentes se prefiere la ruta explicita.

## Pipeline analitico completo

Ejecutar los tres proyectos en el orden recomendado:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_analysis_pipeline
```

Forzar XGBoost en nowcast de produccion para demo:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_analysis_pipeline --production-force-model xgboost
```

La corrida reconstruye `data/analysis/master_price_workbook.xlsx` y escribe:

- `data/analysis/water_risk/dam_decena_features.parquet`
- `data/analysis/production_nowcast/crop_state_cutoff_features.parquet`
- `data/analysis/price_shock/price_product_market_daily_features.parquet`
- Reportes HTML y graficos PNG para nowcast de produccion y alerta de precios, ademas de los workbooks Excel.
- Reportes CSV, XLSX, HTML, PNG, metricas JSON y modelos candidatos bajo cada carpeta.

En el nowcast de produccion, los reportes ejecutivos muestran la variacion esperada contra una base de comparacion visible: primero `anio anterior` y, si falta, `promedio 5 anios`. Cuando no existe referencia suficiente, el reporte marca `s/d`.

La seleccion del metodo operativo se realiza con un corte temporal. Si XGBoost no supera el mejor baseline en MAE fuera de muestra, el reporte usa el baseline y conserva XGBoost solo como artefacto candidato.

En la version actual del monitor hidrico, el historial reforzado de presas permite que el modelo operativo use un enfoque por deltas (`xgboost_delta`) en `30`, `60` y `90` dias. El HTML y el XLSX dejan visible el metodo por horizonte, el cambio pronosticado frente al valor actual y muestran todas las presas evaluadas en la tabla, no solo una muestra.

En nowcast de produccion tambien existe un override de demo. Si fuerzas `--production-force-model xgboost`, la salida deja trazabilidad explicita de que el metodo fue forzado y no debe presentarse como validado por backtesting.

### Enriquecimiento climatico

Descargar NASA POWER para las coordenadas de las presas:

```powershell
python -m scripts.fetch_nasa_power_weather --start-date 2025-01-01 --end-date 2026-06-15
```

Backfill anual del historico nacional de presas:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_historical_backfill --start-year 1999 --end-year 2026
```

Usar el archivo climatico en la corrida integrada:

```powershell
python -m scripts.run_analysis_pipeline `
  --climate-file data/raw/climate/nasa_power_decena.parquet
```

Forzar un metodo operativo de riesgo hidrico para demo:

```powershell
python -m scripts.run_water_risk_model --force-model xgboost_delta
```

Importante:

- `--force-model` es solo para demo o inspeccion.
- Si se usa, la salida de riesgo hidrico deja trazabilidad explicita de que el metodo fue forzado.
- No debe presentarse como metodo operativo validado si el backtesting no lo favorece.
- El clima NASA debe mantenerse como enriquecimiento opcional: si empeora el MAE fuera de muestra en un horizonte, no debe quedarse como input operativo solo por intuicion.

### Precios internacionales publicos

Esta capa no usa API keys, tokens ni fuentes pagadas. Descarga directamente World Bank Pink Sheet y FRED USD/MXN; USDA AMS e IMF se consumen desde archivos publicos CSV/XLS/XLSX colocados manualmente en las carpetas indicadas.

Descargar fuentes publicas directas:

```powershell
python -m scripts.fetch_public_international_prices --output-root data/raw/international_prices
```

Coloca descargas publicas adicionales en:

- `data/raw/international_prices/usda_ams/`
- `data/raw/international_prices/imf/`

Construir el parquet de features:

```powershell
python -m scripts.build_international_price_features `
  --config config/products.xlsx `
  --raw-root data/raw/international_prices `
  --output data/analysis/international_prices/international_price_features.parquet
```

Usarlo en la corrida integrada:

```powershell
python -m scripts.run_analysis_pipeline `
  --international-features data/analysis/international_prices/international_price_features.parquet
```

La hoja `proxies_internacionales` de `config/products.xlsx` controla que proxies son `feature` y cuales quedan como `diagnostico_only`. Los proxies debiles no entran al modelo salvo que se cambie explicitamente la configuracion y el backtesting temporal justifique su uso.

### 1. SNIIM

Ejemplo:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format xlsx
```

Ejemplo en CSV:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format csv
```

Ejemplo en XLS:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format xls
```

Con parametros opcionales:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 233 --origen-id -1 --destino-id -1 --precios-por-id 2 --output-dir data/raw/sniim --output-format xlsx
```

Salida esperada:

- `--output-format csv` genera `.csv`
- `--output-format xls` genera `.xls`
- `--output-format xlsx` genera `.xlsx`
- Nombre tipo `sniim_producto_<producto_id>_<fecha_inicio>_<fecha_final>.<ext>`
- La salida SNIIM incluye `producto_sniim`, que guarda el nombre exacto mostrado por el sitio en la cabecera del reporte, por ejemplo `Aguacate Hass`
- Ejecuta SNIIM con `python -m src.extract.sniim` desde la raiz del repo; `python src/extract/sniim.py ...` rompe los imports del paquete actual

### 2. Cierre Agricola SIAP por HTTP

Ejemplo:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xls
```

Ejemplo en CSV:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format csv
```

Ejemplo en XLSX:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xlsx
```

Con modo debug:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xls --debug --debug-dir debug_cierre_agricola
```

Salida esperada:

- `--output-format xls` genera un archivo `.xls`
- `--output-format csv` genera un archivo `.csv`
- `--output-format xlsx` genera un archivo `.xlsx`
- Si `--output` no trae la extension correcta, el script la ajusta automaticamente
- El portal suele devolver una tabla HTML compatible con Excel en lugar de un binario XLS nativo; esto es esperado en esta fuente
- XML/HTML de depuracion en `debug_cierre_agricola/` si usas `--debug`
- `debug_cierre_agricola/funciones_cierre.js` es solo una referencia del JavaScript original del portal para entender el flujo xajax; no se ejecuta como parte del scraper Python
- La salida normalizada ahora conserva `cultivo_cierre_agricola_original` y `unidad_cierre_agricola` para poder reutilizar PMR anual de forma trazable en analisis comparativos
- Ejecuta Cierre Agricola con `python -m src.extract.cierre_agricola_requests` desde la raiz del repo; no uses `python src.extract.cierre_agricola_requests.py ...`

### 2.1. Cierre Agricola por lote para alimentar el workbook maestro

Si quieres poblar rapido los PMR anuales para los productos canonicos del `config/products.xlsx`, usa el batch runner:

```powershell
python -m scripts.fetch_cierre_batch --config config/products.xlsx --output-root data/raw/cierre_agricola_batch --years 2023 2024 --output-format xlsx
```

Salida esperada:

- Un archivo por `producto_canonico` y por año dentro de `data/raw/cierre_agricola_batch/`
- Cada corrida crea una subcarpeta `run_YYYYMMDD_HHMMSS_years_<years>/`
- El resumen queda dentro de esa subcarpeta como `batch_summary.json`
- Si `cultivo_cierre_agricola` viene vacio en la configuracion, el script usa un fallback interno para los 10 productos canonicos actuales

Despues de generar ese lote, reconstruye el workbook maestro con:

```powershell
python -m scripts.build_master_price_workbook --daily-root data/daily_runs --avance-root data/raw/avance_agricola_batch --cierre-root data/raw/cierre_agricola_batch --output data/analysis/master_price_workbook.xlsx
```

### 2.2. Avance Agricola SIAP por HTTP

Este flujo replica la variante `Por ubicacion geografica -> Por Entidad Federativa` y deja fijos estos filtros:

- `Ciclo = Ciclicos - Perennes`
- `Modalidad = Riego + Temporal`
- `Entidad federativa = Nacional`
- `Tipo de agricultura = Todo`
- `Tipo de produccion = Todo`
- `Tipo de mercado = Todo`

Solo necesitas pasar `year`, `month` y `crop`.

Ejemplo:

```powershell
python -m src.extract.avance_agricola_requests --year 2026 --month Febrero --crop Aguacate --output-format xlsx
```

Ejemplo con valor numerico del mes:

```powershell
python -m src.extract.avance_agricola_requests --year 2026 --month 2 --crop Aguacate --output-format csv
```

Con salida explicita y debug:

```powershell
python -m src.extract.avance_agricola_requests --year 2026 --month Febrero --crop Aguacate --output data/raw/avance_agricola/aguacate_2026_febrero --output-format xlsx --debug --debug-dir debug_avance_agricola
```

Salida esperada:

- Si no pasas `--output`, el script guarda en `data/raw/avance_agricola/`
- `--output-format xls` genera un `.xls`
- `--output-format csv` genera un `.csv`
- `--output-format xlsx` genera un `.xlsx`
- La salida normalizada conserva `cultivo_avance_agricola_original`, `unidad_avance_agricola`, `anio_consulta`, `mes_consulta`, `mes_consulta_nombre` y `situacion_corte`
- Igual que Cierre, el portal suele devolver una tabla HTML compatible con Excel en lugar de un binario XLS nativo
- Ejecuta Avance con `python -m src.extract.avance_agricola_requests` desde la raiz del repo

### 2.3. Avance Agricola por lote desde `products.xlsx`

Si quieres bajar un mismo mes para todos los productos configurados con `avance_agricola_habilitado = TRUE`, usa el batch runner:

```powershell
python -m scripts.fetch_avance_batch --config config/products.xlsx --year 2026 --month Febrero --output-root data/raw/avance_agricola_batch --output-format xlsx
```

Salida esperada:

- Un archivo por `producto_canonico` dentro de `data/raw/avance_agricola_batch/`
- Cada corrida crea una subcarpeta `run_YYYYMMDD_HHMMSS_<anio>_<mes>/`
- El resumen queda dentro de esa subcarpeta como `batch_summary.json`
- Solo se procesan filas activas con `cultivo_avance_agricola` lleno

### 2.4. Historico interno de siembras/cosechas a formato Avance-like

Si cuentas con el CSV interno `siembras_cosechas_*.csv`, puedes convertirlo a XLSX compatibles con el nowcast de produccion:

```powershell
python -m scripts.normalize_company_avance_history `
  --input data/raw/avance_agricola_batch/siembras_cosechas_202606171814.csv `
  --output-root data/raw/avance_agricola_batch/company_historical_avance `
  --years 2023 2024
```

El adaptador:

- Genera archivos `*.xlsx` por `cultivo + anio` bajo `data/raw/avance_agricola_batch/company_historical_avance/`
- Conserva solo meses `enero..diciembre` del mismo anio agricola para no forzar cortes cruzados de calendario en el pipeline actual
- Mapea `SIEMBRA -> superficie_sembrada_ha` y `COSECHA -> superficie_cosechada_ha`
- Deja `superficie_siniestrada_ha`, `produccion` y `rendimiento` vacios porque ese CSV no los contiene
- Recorta sufijos finales de ceros despues del ultimo acumulado positivo para evitar cierres espurios en el entrenamiento historico

### 3. Cierre Agricola SIAP con Playwright

Usa esta variante si el flujo por HTTP falla por cambios en la pagina o por comportamiento del frontend.

```powershell
python -m src.extract.scraper_cierre_agricola_playwright --year 2024 --crop Aguacate --download-dir data/raw/cierre_agricola
```

Salida esperada:

- Archivo descargado en el directorio indicado por `--download-dir`

### 4. Walmart produce scraper

Por default, este script ahora intenta leer `config/products.xlsx` y usa las filas activas con `walmart_habilitado = TRUE` para que los terminos de busqueda coincidan con la corrida diaria. Si el archivo no existe, cae al catalogo hardcodeado legado.

Ejemplo:

```powershell
python -m src.extract.walmart_produce_scraper --output-format csv
```

Ejemplo en XLS:

```powershell
python -m src.extract.walmart_produce_scraper --output-format xls
```

Ejemplo en XLSX:

```powershell
python -m src.extract.walmart_produce_scraper --output-format xlsx
```

Con ruta explicita:

```powershell
python -m src.extract.walmart_produce_scraper --output-format xlsx --output data/raw/walmart/walmart_produce_latest.xlsx
```

Con un workbook de configuracion explicito:

```powershell
python -m src.extract.walmart_produce_scraper --config config/products.xlsx --output-format xlsx
```

Salida esperada:

- Un archivo en formato `csv`, `xls` o `xlsx`
- Si no pasas `--output`, el script guarda en `data/raw/walmart/` con un nombre tipo `walmart_produce_YYYYMMDD_HHMMSS.<ext>`
- El script imprime en consola los registros seleccionados por cultivo
- Si `config/products.xlsx` existe, usa `terminos_busqueda_walmart` igual que la corrida diaria; por ejemplo, `Papa` puede buscar `papa blanca` en lugar del fallback legado `papa`
- Cuando el script corre con producto configurado, descarta resultados cuyo nombre infiera claramente otro cultivo; esto evita que un resultado como jitomate quede etiquetado como aguacate solo por venir de la misma busqueda

### 4.1. Presas Agricolas

Este scraper reproduce el flujo HTTP real del portal sin depender del iframe ni del clic interactivo del mapa:

- `js/funciones.php` devuelve el corte de todas las presas para un `anio + mes + decena`.
- `js/graf.php` devuelve la serie historica de una presa para un `id_conagua + mes + decena + rango de anios`.
- `config/presas_agricolas.xlsx` sirve como documento editable de parametros.
- `config/presas_agricolas.xlsx` ahora incluye una hoja `catalogo_presas` para buscar `id_conagua` por `nombre_oficial` y `estado`.
- `--catalog-scope latest` arma el catalogo solo con el ultimo corte publicado.
- `--catalog-scope all-available` intenta unir todos los periodos historicos publicados y agrega metadatos como `periodos_observados`, `anio_primer_avistamiento` y `anio_ultimo_avistamiento`.

Ejecutar con la configuracion del archivo config/presas_agricolas.xlsx:

```powershell
python -m src.extract.presas_agricolas --config config/presas_agricolas.xlsx
```

Ejecutar con salida explicita:

```powershell
python -m src.extract.presas_agricolas --config config/presas_agricolas.xlsx --output data/raw/presas_agricolas/presas_historicas.xlsx
```

Crear o regenerar el workbook de configuracion:

```powershell
python -m src.extract.presas_agricolas --init-config
```

Generar un catalogo maestro mas fuerte, uniendo todos los periodos publicados disponibles:

```powershell
python -m src.extract.presas_agricolas --init-config --overwrite-config --catalog-scope all-available
```

Salida esperada:

- Un workbook `.xlsx` en `data/raw/presas_agricolas/` con hojas `presas_periodo`, `series_presa`, `errores` y `metadatos`
- `config/presas_agricolas.xlsx` trae filas listas para usar desde el primer momento:
  - `corte_nacional_actual`: snapshot del ultimo periodo publicado por el portal
  - `presas_tamaulipas_actual`: ejemplo de lote por estado para el mismo corte
  - `serie_pedro_jose_mendez`: ejemplo historico para la presa `3524`
- En `consultas`, usa `tipo_consulta = presas_periodo` para el corte nacional, `tipo_consulta = presas_estado` para traer todas las presas de una entidad en esa fecha, y `tipo_consulta = serie_presa` para el historico por presa
- Puedes dejar `id_conagua` vacio y llenar `nombre_oficial` + `estado`; el script intenta resolver el identificador automaticamente contra `catalogo_presas`
- Para `serie_presa`, si `anio_inicial` queda vacio, el script usa una ventana automatica de 10 anios
- Para `presas_periodo`, si llenas `anio_final`, el script descarga todos los cortes desde `anio`/`mes`/`decena` hasta el fin de ese anio (limitado al ultimo periodo publicado cuando aplica). Deja `anio_final` vacio para un solo corte
- Si llenas `id_conagua` en una fila `presas_periodo`, el resultado se filtra a esa sola presa dentro del corte solicitado
- En `presas_estado`, `estado` es obligatorio y el resultado queda filtrado exactamente a esa entidad
- Si un `nombre_oficial` coincide con varias presas, agrega `estado` o usa `id_conagua` directo para evitar ambiguedad

### 4.2. Wrapper automatizable por decena

Cuando solo necesitas guardar el corte nacional de presas cada diez dias para un worker, cron o Task Scheduler, usa el wrapper operativo:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_decena_snapshot
```

Forzar un periodo explicito:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_decena_snapshot --year 2026 --month 6 --decena 3
```

Resolver la decena a partir de una fecha:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_decena_snapshot --target-date 2026-06-27
```

Forzar una redescarga aunque ya exista ese periodo:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_decena_snapshot --year 2026 --month 6 --decena 3 --force
```

Comportamiento esperado:

- El script genera una configuracion minima en Excel con `tipo_consulta = presas_periodo` y llama al extractor existente.
- La salida por default vive en `data/raw/presas_agricolas/decena/YYYY/MM/`.

Cuando necesitas reforzar el entrenamiento del monitor hidrico con historia nacional completa por decena, usa el backfill anual:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_historical_backfill --start-year 1999 --end-year 2026
```

Comportamiento esperado:

- Genera un workbook anual por anio bajo `data/raw/presas_agricolas/backfill/`.
- Reusa `run_from_config` del extractor de presas; no introduce otro scraper.
- Escribe `backfill_summary.json` con el resumen agregado de la corrida.
- Si ya existe un anio descargado, lo salta salvo que pases `--force`.
- Cada ejecucion exitosa guarda tres artefactos por corrida: workbook `.xlsx`, config `.xlsx` y resumen `.json`.
- Si ya existe un workbook para la misma combinacion `anio + mes + decena`, la corrida se marca como `skipped_existing` y no vuelve a descargar salvo que pases `--force`.
- El resumen JSON deja trazabilidad con `run_timestamp`, periodo objetivo, `status`, rutas de salida, `row_count` y `error_count`.
- Si el extractor base escribe filas en la hoja `errores`, el wrapper marca la corrida como `error` o `partial_error` y termina con codigo de salida no-cero para que un scheduler detecte el fallo.

### 5. Chedraui produce scraper

Ejemplo:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format csv
```

Ejemplo en XLS:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format xls
```

Ejemplo en XLSX:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format xlsx
```

Con ruta explicita:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format xlsx --output data/raw/chedraui/chedraui_produce_latest.xlsx
```

Salida esperada:

- Un archivo en formato `csv`, `xls` o `xlsx`
- Si no pasas `--output`, el script guarda en `data/raw/chedraui/` con un nombre tipo `chedraui_produce_YYYYMMDD_HHMMSS.<ext>`
- El script imprime en consola los registros seleccionados por cultivo

## Extraccion diaria

Hay un runner diario que lee un workbook editable por el usuario y genera salidas consolidadas en XLSX para Walmart, Chedraui, SNIIM y Cierre Agricola.

### Archivo de configuracion

Template incluido:

```powershell
config/products.xlsx
```

Sheet requerida:

- `productos`

Sheet opcional:

- `proxies_internacionales`

Columnas requeridas:

- `activo`
- `producto_canonico`
- `walmart_habilitado`
- `terminos_busqueda_walmart`
- `sniim_habilitado`
- `sniim_id_producto`
- `sniim_id_origen`
- `sniim_id_destino`
- `sniim_id_precios_por`
- `cierre_agricola_habilitado`
- `cultivo_cierre_agricola`

Columnas opcionales (para habilitar Chedraui):

- `chedraui_habilitado`
- `terminos_busqueda_chedraui`
- `avance_agricola_habilitado`
- `cultivo_avance_agricola`

Columnas de `proxies_internacionales`:

- `activo`
- `producto_canonico`
- `proxy_id`
- `fuente`
- `serie`
- `tipo_proxy`
- `uso_modelo`
- `frecuencia`
- `moneda`
- `unidad_origen`
- `nota_metodologica`

Reglas importantes:

- `activo = FALSE` omite toda la fila
- `terminos_busqueda_walmart` acepta valores separados por `|`
- `terminos_busqueda_chedraui` acepta valores separados por `|`
- Si `terminos_busqueda_walmart` esta vacio y Walmart esta habilitado, se usa `producto_canonico`
- Si `terminos_busqueda_chedraui` esta vacio y Chedraui esta habilitado, se usa `producto_canonico`
- Si `sniim_id_origen`, `sniim_id_destino` o `sniim_id_precios_por` estan vacios, se usan `-1`, `-1` y `2`
- Si una fila habilita una fuente pero le falta un mapping requerido, la corrida continua y el error queda en `run_summary.json`

### Correr el runner diario manualmente

```powershell
python scripts/run_daily_extracts.py --config config/products.xlsx --output-root data/daily_runs
```

Con fecha fija:

```powershell
python scripts/run_daily_extracts.py --config config/products.xlsx --output-root data/daily_runs --run-date 2026-04-08
```

Comportamiento:

- Walmart toma snapshot del dia de corrida
- SNIIM consulta el dia anterior
- Cierre Agricola usa el año de `run-date`
- El runner continua aunque falle una fila o una fuente

Salida esperada por corrida:

- `data/daily_runs/YYYY-MM-DD/walmart_YYYY-MM-DD.xlsx`
- `data/daily_runs/YYYY-MM-DD/chedraui_YYYY-MM-DD.xlsx`
- `data/daily_runs/YYYY-MM-DD/sniim_YYYY-MM-DD.xlsx`
- `data/daily_runs/YYYY-MM-DD/cierre_agricola_YYYY-MM-DD.xlsx`
- `data/daily_runs/YYYY-MM-DD/products_snapshot.xlsx`
- En el XLSX de SNIIM, la hoja `datos` tambien conserva `producto_sniim` para distinguir el nombre real desplegado por SNIIM del producto canonico configurado
- `data/daily_runs/YYYY-MM-DD/run_summary.json`

Cada workbook consolidado genera:

- Sheet `datos`
- Sheet `errores` si hubo errores
- Sheet `metadatos`

## Workbook maestro comparativo

Despues de tener `data/daily_runs` y un directorio de exportes normalizados de Avance Agricola, puedes construir un workbook maestro para comparacion diaria y EDA. Cierre Agricola queda como insumo secundario opcional.

Comando:

```powershell
python -m scripts.build_master_price_workbook --daily-root data/daily_runs --avance-root data/raw/avance_agricola_batch --cierre-root data/raw/cierre_agricola_batch --output data/analysis/master_price_workbook.xlsx
```

Salida esperada:

- `data/analysis/master_price_workbook.xlsx`
- Sheet `panel_daily_long`
- Sheet `compare_daily_wide`
- Sheet `sniim_daily_stats`
- Sheet `avance_monthly_stats`
- Sheet `avance_entity_monthly`
- Sheet `cierre_annual_stats`
- Sheet `precios_internacionales`
- Sheet `cobertura_internacional`
- Sheet `mapa_proxies`
- Sheet `coverage`

Reglas del workbook maestro:

- SNIIM agrega `precio_frecuente` por `fecha_corrida + producto_canonico` con media, mediana, minimo, maximo y conteo
- Walmart y Chedraui usan `precio_estimado_por_kg_mxn` cuando existe; si no, caen a `precio_mxn`
- El constructor normaliza `canonical_product` a una llave ASCII en minusculas con guiones bajos antes de unir fuentes; por ejemplo, `Aguacate` y `aguacate` se consolidan como `aguacate`
- Avance Agricola agrega contexto mensual por producto y lo replica sobre las filas diarias del mismo mes para poder analizar precios contra produccion, superficie cosechada, siniestralidad y rendimiento
- Cierre Agricola calcula PMR anual ponderado por produccion y queda como referencia anual secundaria cuando se pasa `--cierre-root`
- Los precios internacionales se agregan como contexto auditable cuando se pasa `--international-features`; los joins usan `fecha_disponible` para evitar fuga de informacion futura.
- El notebook `notebooks/master_price_eda.ipynb` usa un eje de fechas mensual en las graficas agregadas y no comparte ese eje con la grafica diaria; asi se evitan conflictos de unidades en Matplotlib. En la grafica diaria con contexto de Avance, cada valor mensual se dibuja solo dentro de su propio mes en vez de arrastrarse hasta el siguiente dato disponible
- El notebook `notebooks/master_price_eda.ipynb` ahora lee `compare_daily_wide`, `avance_monthly_stats`, `avance_entity_monthly`, `coverage` y opcionalmente `cierre_annual_stats`, con comentarios y figuras en español

## Windows Task Scheduler

Para este proyecto en tu maquina local, usa Windows Task Scheduler en lugar de cron de WSL.

Nombre de la tarea:

- `AgroPrecios Daily Extract`

Recomendacion: registra la tarea con PowerShell `ScheduledTasks` en lugar de `schtasks /Create` para poder habilitar:

- ejecucion aunque no hayas iniciado sesion
- `StartWhenAvailable` para intentar correr una tarea perdida cuando la maquina vuelva a estar disponible
- `WakeToRun` para intentar despertar la laptop si estaba suspendida

### Registrar o reemplazar la tarea recomendada

Ejecuta PowerShell como administrador y corre:

```powershell
$taskName = "AgroPrecios Daily Extract"
$taskUser = "$env:COMPUTERNAME\$env:USERNAME"
$taskPassword = Read-Host "Windows password for $taskUser"

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios\scripts\run_daily_extracts_task.cmd"

$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At 06:00AM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $taskUser `
    -Password $taskPassword `
    -RunLevel Limited `
    -Force
```

Notas:

- `-Force` reemplaza la tarea existente con el mismo nombre
- Si quieres cambiar la hora a `04:00 PM`, cambia `-At 06:00AM` por `-At 04:00PM` y vuelve a ejecutar el bloque
- Esta configuracion requiere la contrasena de Windows del usuario porque la tarea queda lista para correr aunque no tengas sesion abierta

### Comportamiento esperado

- Si la laptop esta encendida a las `06:00`, la tarea corre en ese momento
- Si la laptop esta suspendida, `WakeToRun` intentara despertarla; depende de que Windows y el hardware permitan wake timers
- Si la laptop esta apagada o hibernada, no puede correr exactamente a las `06:00`
- Si la hora programada se pierde porque la maquina no estaba disponible, `StartWhenAvailable` hace que Windows intente correrla cuando el equipo vuelva a estar disponible
- No es una garantia de tiempo exacto; el catch-up ocurre "tan pronto como sea posible" segun Task Scheduler

### Verificacion

```cmd
schtasks /Query /TN "AgroPrecios Daily Extract" /V /FO LIST
```

Puntos a revisar en la salida:

- `Modo de inicio de sesion` no debe quedar en `Solo interactivo`
- `Hora proxima ejecucion` debe reflejar la siguiente corrida
- `Ultimo resultado: 0` indica ejecucion exitosa

### Correrla manualmente una vez

```cmd
schtasks /Run /TN "AgroPrecios Daily Extract"
```

Notas operativas:

- La tarea usa el Python del virtualenv local del proyecto
- Usa `scripts\run_daily_extracts_task.cmd` para evitar el limite de longitud de argumentos y fijar `cwd`
- Los logs se escriben en `logs/daily_extracts.log`
- El runner sale con codigo no cero si no puede iniciar o si ninguna fuente tuvo resultados exitosos
- Si hubo resultados parciales, igual se escriben los XLSX y el `run_summary.json`

## Tests

Para correr las pruebas actuales:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

O por modulo:

```powershell
python -m unittest tests.test_sniim
python -m unittest tests.test_walmart_produce_scraper
```

## Notas y limitaciones

- Los scrapers dependen de sitios externos y pueden romperse si cambia el HTML o el flujo del formulario.
- Walmart puede bloquear solicitudes automatizadas en ciertos momentos.
- Cierre Agricola es especialmente fragil porque usa un flujo legado con xajax.
- El repo todavia esta mas cerca de una base de extraccion validada que de un producto de forecast completo.
