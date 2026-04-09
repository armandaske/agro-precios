# Agro precios

POC para extraer y preparar datos de precios agroalimentarios en Mexico.

Hoy el repositorio esta centrado principalmente en la capa de extraccion. Ya hay scrapers funcionales para fuentes publicas clave y pruebas para parte del parsing, pero todavia no existe un pipeline completo de transformacion, modelado y forecast como producto final.

## Estado actual del repo

Implementado:

- Extraccion de precios de frutas y hortalizas desde SNIIM via `requests`.
- Descarga de reportes de Cierre Agricola SIAP via flujo HTTP/xajax.
- Alternativa con Playwright para Cierre Agricola cuando el flujo HTTP no sea suficiente.
- Scraper de precios de productos frescos de Walmart Mexico.
- Tests unitarios para parsing de SNIIM y Walmart.

No implementado aun como flujo formal:

- Pipeline end-to-end de transformacion.
- Feature engineering para forecast.
- Entrenamiento de modelos.
- Script orquestador tipo `run_all.py`.

## Estructura relevante

- `src/extract/sniim.py`: extractor SNIIM y export a CSV/XLSX.
- `src/extract/cierre_agricola_requests.py`: scraper HTTP para Cierre Agricola.
- `src/extract/scraper_cierre_agricola_playwright.py`: alternativa con navegador.
- `src/extract/walmart_produce_scraper.py`: scraper de frutas y verduras en Walmart.
- `scripts/run_daily_extracts.py`: orquestador diario para las 3 fuentes.
- `config/products.xlsx`: workbook editable por el usuario con la configuracion de productos.
- `tests/`: pruebas unitarias.
- `data/raw/sniim/`: salidas generadas por el extractor SNIIM.
- `debug_cierre_agricola/`: respuestas de depuracion del scraper de Cierre Agricola.

## Requisitos

- Python 3.10+ recomendado.
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

### 1. SNIIM

Ejemplo:

```powershell
python src/extract/sniim.py --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format xlsx
```

Ejemplo en CSV:

```powershell
python src/extract/sniim.py --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format csv
```

Ejemplo en XLS:

```powershell
python src/extract/sniim.py --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format xls
```

Con parametros opcionales:

```powershell
python src/extract/sniim.py --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 233 --origen-id -1 --destino-id -1 --precios-por-id 2 --output-dir data/raw/sniim --output-format xlsx
```

Salida esperada:

- `--output-format csv` genera `.csv`
- `--output-format xls` genera `.xls`
- `--output-format xlsx` genera `.xlsx`
- Nombre tipo `sniim_producto_<producto_id>_<fecha_inicio>_<fecha_final>.<ext>`

### 2. Cierre Agricola SIAP por HTTP

Ejemplo:

```powershell
python src/extract/cierre_agricola_requests.py --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xls
```

Ejemplo en CSV:

```powershell
python src/extract/cierre_agricola_requests.py --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format csv
```

Ejemplo en XLSX:

```powershell
python src/extract/cierre_agricola_requests.py --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xlsx
```

Con modo debug:

```powershell
python src/extract/cierre_agricola_requests.py --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xls --debug --debug-dir debug_cierre_agricola
```

Salida esperada:

- `--output-format xls` genera un archivo `.xls`
- `--output-format csv` genera un archivo `.csv`
- `--output-format xlsx` genera un archivo `.xlsx`
- Si `--output` no trae la extension correcta, el script la ajusta automaticamente
- El portal suele devolver una tabla HTML compatible con Excel en lugar de un binario XLS nativo; esto es esperado en esta fuente
- XML/HTML de depuracion en `debug_cierre_agricola/` si usas `--debug`

### 3. Cierre Agricola SIAP con Playwright

Usa esta variante si el flujo por HTTP falla por cambios en la pagina o por comportamiento del frontend.

```powershell
python src/extract/scraper_cierre_agricola_playwright.py --year 2024 --crop Aguacate --download-dir data/raw/cierre_agricola
```

Salida esperada:

- Archivo descargado en el directorio indicado por `--download-dir`

### 4. Walmart produce scraper

Ejemplo:

```powershell
python src/extract/walmart_produce_scraper.py --output-format csv
```

Ejemplo en XLS:

```powershell
python src/extract/walmart_produce_scraper.py --output-format xls
```

Ejemplo en XLSX:

```powershell
python src/extract/walmart_produce_scraper.py --output-format xlsx
```

Con ruta explicita:

```powershell
python src/extract/walmart_produce_scraper.py --output-format xlsx --output data/raw/walmart/walmart_produce_latest.xlsx
```

Salida esperada:

- Un archivo en formato `csv`, `xls` o `xlsx`
- Si no pasas `--output`, el script genera un nombre tipo `walmart_produce_YYYYMMDD_HHMMSS.<ext>`
- El script imprime en consola los registros seleccionados por cultivo

## Extraccion diaria

Hay un runner diario que lee un workbook editable por el usuario y genera salidas consolidadas en XLSX para Walmart, SNIIM y Cierre Agricola.

### Archivo de configuracion

Template incluido:

```powershell
config/products.xlsx
```

Sheet requerida:

- `products`

Columnas requeridas:

- `active`
- `canonical_product`
- `walmart_enabled`
- `walmart_search_terms`
- `sniim_enabled`
- `sniim_producto_id`
- `sniim_origen_id`
- `sniim_destino_id`
- `sniim_precios_por_id`
- `cierre_enabled`
- `cierre_crop_name`

Reglas importantes:

- `active = FALSE` omite toda la fila
- `walmart_search_terms` acepta valores separados por `|`
- Si `walmart_search_terms` esta vacio y Walmart esta habilitado, se usa `canonical_product`
- Si `sniim_origen_id`, `sniim_destino_id` o `sniim_precios_por_id` estan vacios, se usan `-1`, `-1` y `2`
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
- `data/daily_runs/YYYY-MM-DD/sniim_YYYY-MM-DD.xlsx`
- `data/daily_runs/YYYY-MM-DD/cierre_agricola_YYYY-MM-DD.xlsx`
- `data/daily_runs/YYYY-MM-DD/products_snapshot.xlsx`
- `data/daily_runs/YYYY-MM-DD/run_summary.json`

Cada workbook consolidado genera:

- Sheet `data`
- Sheet `failures` si hubo errores
- Sheet `meta`

## Windows Task Scheduler

Para este proyecto en tu maquina local, usa Windows Task Scheduler en lugar de cron de WSL.

Nombre de la tarea:

- `AgroPrecios Daily Extract`

Comando exacto para registrar la tarea:

```cmd
schtasks /Create /SC DAILY /ST 06:00 /TN "AgroPrecios Daily Extract" /TR "cmd /c C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios\scripts\run_daily_extracts_task.cmd" /F
```

Verificacion:

```cmd
schtasks /Query /TN "AgroPrecios Daily Extract" /V /FO LIST
```

Para correrla manualmente una vez:

```cmd
schtasks /Run /TN "AgroPrecios Daily Extract"
```

Notas operativas:

- La tarea corre diario a las `06:00`
- Usa el Python del virtualenv local del proyecto
- Usa `scripts\run_daily_extracts_task.cmd` para evitar el limite de longitud de `/TR` en `schtasks`
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
