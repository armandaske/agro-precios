# Agro precios

POC para extraer y preparar datos de precios agroalimentarios en Mexico.

Hoy el repositorio esta centrado principalmente en la capa de extraccion. Ya hay scrapers funcionales para fuentes publicas clave y pruebas para parte del parsing, pero todavia no existe un pipeline completo de transformacion, modelado y forecast como producto final.

## Guia para agentes y mantenimiento de docs

- Revisa `AGENTS.md` antes de hacer cambios importantes; ahi vive la guia operativa especifica del repo para agentes Codex.
- Cada vez que un agente cree o modifique algo que valga la pena documentar, debe actualizar `README.md` y `AGENTS.md` en el mismo cambio para evitar que las instrucciones queden desfasadas.
- Todo texto orientado al usuario debe quedar en espanol por defecto: titulos, etiquetas, graficas, nombres de columnas, nombres de hojas y salidas visibles para analisis o consumo de negocio.

## Estado actual del repo

Implementado:

- Extraccion de precios de frutas y hortalizas desde SNIIM via `requests`.
- Descarga de reportes de Cierre Agricola SIAP via flujo HTTP/xajax.
- Alternativa con Playwright para Cierre Agricola cuando el flujo HTTP no sea suficiente.
- Scraper de precios de productos frescos de Walmart Mexico.
- Scraper de precios de productos frescos de Chedraui Mexico.
- Tests unitarios para parsing de SNIIM, Walmart y Chedraui.

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
- `src/extract/chedraui_produce_scraper.py`: scraper de frutas y verduras en Chedraui.
- `scripts/run_daily_extracts.py`: orquestador diario para las 4 fuentes.
- `scripts/fetch_cierre_batch.py`: descarga en lote exportes normalizados de Cierre Agricola para los productos canonicos configurados.
- `scripts/build_master_price_workbook.py`: constructor del workbook maestro comparativo para SNIIM, Walmart, Chedraui y Cierre Agricola.
- `config/products.xlsx`: workbook editable por el usuario con la configuracion de productos.
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
- Un resumen en `data/raw/cierre_agricola_batch/batch_summary.json`
- Si `cultivo_cierre_agricola` viene vacio en la configuracion, el script usa un fallback interno para los 10 productos canonicos actuales

Despues de generar ese lote, reconstruye el workbook maestro con:

```powershell
python -m scripts.build_master_price_workbook --daily-root data/daily_runs --cierre-root data/raw/cierre_agricola_batch --output data/analysis/master_price_workbook.xlsx
```

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

Despues de tener `data/daily_runs` y un directorio de exportes normalizados de Cierre Agricola, puedes construir un workbook maestro para comparacion diaria y EDA.

Comando:

```powershell
python -m scripts.build_master_price_workbook --daily-root data/daily_runs --cierre-root data/raw/cierre_agricola --output data/analysis/master_price_workbook.xlsx
```

Salida esperada:

- `data/analysis/master_price_workbook.xlsx`
- Sheet `panel_daily_long`
- Sheet `compare_daily_wide`
- Sheet `sniim_daily_stats`
- Sheet `cierre_annual_stats`
- Sheet `coverage`

Reglas del workbook maestro:

- SNIIM agrega `precio_frecuente` por `fecha_corrida + producto_canonico` con media, mediana, minimo, maximo y conteo
- Walmart y Chedraui usan `precio_estimado_por_kg_mxn` cuando existe; si no, caen a `precio_mxn`
- Cierre Agricola calcula PMR anual ponderado por produccion y lo repite sobre cada fecha diaria del mismo anio y producto
- El notebook `notebooks/master_price_eda.ipynb` ya viene listo para leer `compare_daily_wide` y graficar comparaciones, spreads y cobertura

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
