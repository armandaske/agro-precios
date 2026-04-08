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
