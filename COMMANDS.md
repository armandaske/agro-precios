# Comandos utiles

Referencia rapida de comandos para los scripts principales de este repositorio.

Ejecuta todo desde la raiz del repo:

```powershell
cd C:\Users\Dell-G3\Documents\Jupyter-projects\Others\agro-precios
```

## Entorno

Crear y activar el entorno virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Ejecutar toda la suite de pruebas:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Ejecutar pruebas puntuales:

```powershell
python -m unittest tests.test_sniim
python -m unittest tests.test_walmart_produce_scraper
```

## Presas Agricolas

Crear el workbook de configuracion:

```powershell
python -m src.extract.presas_agricolas --init-config
```

Regenerar el workbook con un catalogo mas completo:

```powershell
python -m src.extract.presas_agricolas --init-config --overwrite-config --catalog-scope all-available
```

Ejecutar con la configuracion por default:

```powershell
python -m src.extract.presas_agricolas --config config/presas_agricolas.xlsx
```

Con workbook de salida explicito:

```powershell
python -m src.extract.presas_agricolas --config config/presas_agricolas.xlsx --output data/raw/presas_agricolas/presas_historicas.xlsx
```

Parametros utiles:

- `--config`: workbook de configuracion, default `config/presas_agricolas.xlsx`
- `--output`: opcional; si se omite, guarda bajo `data/raw/presas_agricolas/`
- `--init-config`: crea el workbook de configuracion y termina
- `--overwrite-config`: permite sobrescribir al usar `--init-config`
- `--catalog-scope`: `latest` o `all-available`

## SNIIM

Ejecucion estandar:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format xlsx
```

Salida CSV:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 133 --output-format csv
```

Con filtros explicitos y directorio de salida:

```powershell
python -m src.extract.sniim --fecha-inicio 2026-03-03 --fecha-final 2026-03-16 --producto-id 233 --origen-id -1 --destino-id -1 --precios-por-id 2 --output-dir data/raw/sniim --output-format xlsx
```

Parametros utiles:

- `--fecha-inicio` y `--fecha-final`: obligatorios, formato `YYYY-MM-DD`
- `--producto-id`: id de producto en SNIIM
- `--origen-id`, `--destino-id`: opcionales, default `-1`
- `--precios-por-id`: opcional, default `2`
- `--timeout`: opcional, default `60`
- `--output-dir`: opcional, default `data/raw/sniim`
- `--output-format`: `csv`, `xls` o `xlsx`

## SIAP Avance Agricola via HTTP

Ejecucion estandar:

```powershell
python -m src.extract.avance_agricola_requests --year 2026 --month Febrero --crop Aguacate --output-format xlsx
```

Mes numerico:

```powershell
python -m src.extract.avance_agricola_requests --year 2026 --month 2 --crop Aguacate --output-format csv
```

Con salida explicita y depuracion:

```powershell
python -m src.extract.avance_agricola_requests --year 2026 --month Febrero --crop Aguacate --output data/raw/avance_agricola/aguacate_2026_febrero --output-format xlsx --debug --debug-dir debug_avance_agricola
```

Parametros utiles:

- `--year`: obligatorio
- `--month`: obligatorio; acepta el nombre visible del mes o el valor numerico
- `--crop`: obligatorio
- `--output`: opcional; si se omite, guarda bajo `data/raw/avance_agricola/`
- `--output-format`: `xls`, `csv` o `xlsx`
- `--debug`: guarda artefactos del flujo requests/xajax
- `--debug-dir`: directorio de depuracion, default `debug_avance_agricola`

## SIAP Avance Agricola por lote

Descargar un mismo mes para todos los productos habilitados en la configuracion:

```powershell
python -m scripts.fetch_avance_batch --config config/products.xlsx --year 2026 --month Febrero --output-root data/raw/avance_agricola_batch --output-format xlsx
```

Parametros utiles:

- `--config`: workbook de productos, default `config/products.xlsx`
- `--year`: obligatorio
- `--month`: obligatorio
- `--output-root`: carpeta raiz de salida
- `--output-format`: `xls`, `csv` o `xlsx`

## Walmart

Ejecucion por default:

```powershell
python -m src.extract.walmart_produce_scraper --output-format csv
```

Salida XLSX:

```powershell
python -m src.extract.walmart_produce_scraper --output-format xlsx
```

Con archivo de salida explicito:

```powershell
python -m src.extract.walmart_produce_scraper --output-format xlsx --output data/raw/walmart/walmart_produce_latest.xlsx
```

Con workbook de configuracion explicito:

```powershell
python -m src.extract.walmart_produce_scraper --config config/products.xlsx --output-format xlsx
```

Parametros utiles:

- `--config`: opcional, default `config/products.xlsx`
- `--output-format`: `csv`, `xls` o `xlsx`
- `--output`: opcional; si se omite, guarda bajo `data/raw/walmart/`

## Chedraui

Ejecucion por default:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format csv
```

Salida XLSX:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format xlsx
```

Con archivo de salida explicito:

```powershell
python -m src.extract.chedraui_produce_scraper --output-format xlsx --output data/raw/chedraui/chedraui_produce_latest.xlsx
```

Parametros utiles:

- `--output-format`: `csv`, `xls` o `xlsx`
- `--output`: opcional; si se omite, guarda bajo `data/raw/chedraui/`

## Corrida diaria

Ejecutar el flujo diario:

```powershell
python scripts/run_daily_extracts.py --config config/products.xlsx --output-root data/daily_runs
```

Ejecutar con fecha fija:

```powershell
python scripts/run_daily_extracts.py --config config/products.xlsx --output-root data/daily_runs --run-date 2026-04-08
```

Parametros utiles:

- `--config`: workbook de productos
- `--output-root`: carpeta raiz de salida
- `--run-date`: opcional, formato `YYYY-MM-DD`

## Workbook maestro comparativo

Construir el workbook maestro a partir de las corridas diarias y Avance, con Cierre como contexto opcional:

```powershell
python -m scripts.build_master_price_workbook --daily-root data/daily_runs --avance-root data/raw/avance_agricola_batch --cierre-root data/raw/cierre_agricola_batch --output data/analysis/master_price_workbook.xlsx
```

Con precios internacionales publicos:

```powershell
python -m scripts.build_master_price_workbook `
  --daily-root data/daily_runs `
  --avance-root data/raw/avance_agricola_batch `
  --cierre-root data/raw/cierre_agricola_batch `
  --international-features data/analysis/international_prices/international_price_features.parquet `
  --output data/analysis/master_price_workbook.xlsx
```

Parametros utiles:

- `--daily-root`: raiz de corridas diarias
- `--avance-root`: raiz de exportes por lote de Avance
- `--cierre-root`: opcional; raiz de exportes por lote de Cierre
- `--international-features`: opcional; parquet de precios internacionales publicos
- `--output`: ruta del workbook final

## Precios internacionales publicos sin API keys

Descargar fuentes directas publicas:

```powershell
python -m scripts.fetch_public_international_prices --output-root data/raw/international_prices
```

Notas:

- World Bank Pink Sheet y FRED USD/MXN se descargan directamente.
- USDA AMS e IMF se cargan desde archivos publicos CSV/XLS/XLSX colocados en `data/raw/international_prices/usda_ams/` y `data/raw/international_prices/imf/`.
- No se usan tokens, API keys, Banxico SIE ni feeds pagados.

Construir features internacionales:

```powershell
python -m scripts.build_international_price_features `
  --config config/products.xlsx `
  --raw-root data/raw/international_prices `
  --output data/analysis/international_prices/international_price_features.parquet
```

## Analitica predictiva

Ejecutar el flujo completo:

```powershell
python -m scripts.run_analysis_pipeline
```

Con precios internacionales:

```powershell
python -m scripts.run_analysis_pipeline `
  --international-features data/analysis/international_prices/international_price_features.parquet
```

Monitor de riesgo hidrico:

```powershell
python -m scripts.run_water_risk_model `
  --input-root data/raw/presas_agricolas `
  --output-dir data/analysis/water_risk
```

Nowcast de produccion:

```powershell
python -m scripts.run_production_nowcast `
  --avance-root data/raw/avance_agricola_batch `
  --cierre-root data/raw/cierre_agricola_batch `
  --water-features data/analysis/water_risk/state_decena_features.parquet
```

Alerta de precios:

```powershell
python -m scripts.run_price_shock_model `
  --daily-root data/daily_runs `
  --production-forecast data/analysis/production_nowcast/pronostico_produccion_mensual.csv `
  --water-features data/analysis/water_risk/state_decena_features.parquet
```

Con precios internacionales:

```powershell
python -m scripts.run_price_shock_model `
  --daily-root data/daily_runs `
  --international-features data/analysis/international_prices/international_price_features.parquet
```

Descarga opcional de clima NASA POWER:

```powershell
python -m scripts.fetch_nasa_power_weather `
  --start-date 2025-01-01 `
  --end-date 2026-06-15 `
  --output data/raw/climate/nasa_power_decena.parquet
```

## Programador de tareas de Windows

Wrapper local del scheduler:

```powershell
scripts\run_daily_extracts_task.cmd
```

Registrar o reemplazar la tarea programada:

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

## SIAP Cierre Agricola via HTTP

Ejecucion estandar:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xls
```

Salida CSV:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format csv
```

Con artefactos de depuracion:

```powershell
python -m src.extract.cierre_agricola_requests --year 2024 --crop Aguacate --output data/raw/cierre_agricola/aguacate_2024 --output-format xlsx --debug --debug-dir debug_cierre_agricola
```

Parametros utiles:

- `--year`: obligatorio
- `--crop`: obligatorio
- `--output`: ruta base de salida
- `--output-format`: `xls`, `csv` o `xlsx`
- `--debug`: guarda artefactos del flujo requests/xajax
- `--debug-dir`: directorio de depuracion, default `debug_cierre_agricola`

## SIAP Cierre Agricola por lote

Descargar varios anios para los productos canonicos configurados:

```powershell
python -m scripts.fetch_cierre_batch --config config/products.xlsx --output-root data/raw/cierre_agricola_batch --years 2023 2024 --output-format xlsx
```

Parametros utiles:

- `--config`: workbook de productos, default `config/products.xlsx`
- `--output-root`: carpeta raiz de salida
- `--years`: uno o varios anios
- `--output-format`: `xls`, `csv` o `xlsx`

## SIAP Cierre Agricola con Playwright

Usa esta variante si el flujo HTTP falla:

```powershell
python -m src.extract.scraper_cierre_agricola_playwright --year 2024 --crop Aguacate --download-dir data/raw/cierre_agricola
```

Parametros utiles:

- `--year`: obligatorio
- `--crop`: obligatorio
- `--download-dir`: carpeta destino para la descarga

## Notas

- Para los modulos de `src.extract` y la mayoria de scripts en `scripts`, prefiere `python -m ...`.
- La corrida diaria esta documentada y se usa normalmente como `python scripts/run_daily_extracts.py ...`; ese formato sigue siendo valido.
- Las carpetas raw por default son especificas por fuente: `data/raw/walmart/`, `data/raw/chedraui/`, `data/raw/avance_agricola/` y `data/raw/presas_agricolas/`.
- Si cambian flags o entrypoints, actualiza este archivo junto con `README.md` y `AGENTS.md`.
