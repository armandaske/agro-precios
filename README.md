# Agro Price Forecast POC (México)

## Descripción
Este proyecto desarrolla una **prueba de concepto (POC)** para estimar el comportamiento a corto plazo del precio de frutas y hortalizas en México, utilizando datos públicos agrícolas, precios de mercado y variables climáticas.

El objetivo principal es **integrar múltiples fuentes de datos en un dataset estructurado** y evaluar si un modelo sencillo puede generar predicciones útiles en horizontes de 1 a 4 semanas.

Los resultados están diseñados para ser **fácilmente interpretables y utilizables en Excel (.xlsx)** por equipos no técnicos.

---

## Objetivos
- Integrar datos de distintas fuentes públicas en un solo dataset.
- Generar variables relevantes (históricas, estacionales, climáticas).
- Construir un modelo de predicción simple.
- Comparar contra un baseline (último valor o promedio reciente).
- Entregar resultados en formato Excel claro y reutilizable.

---

## Fuentes de datos
- **SNIIM**: precios de mercado de frutas y hortalizas.
- **DGSIAP (Cierre Agrícola)**: estadísticas anuales de producción.
- **DGSIAP (Avance Agrícola)**: progreso mensual de siembra/cosecha.
- **Calendario Agrícola**: estacionalidad de cultivos.
- **Datos climáticos (API)**: temperatura y precipitación.

---


---

## Flujo de trabajo
1. **Extracción**
   - Descarga o scraping de datos desde fuentes públicas.
2. **Transformación**
   - Limpieza, homologación y agregación (principalmente a nivel semanal).
3. **Feature Engineering**
   - Variables de rezago (lags), promedios móviles, estacionalidad y clima.
4. **Modelado**
   - Baseline simple.
   - Modelo de Machine Learning (ej. Random Forest).
5. **Exportación**
   - Generación de archivos Excel con datos, resultados y métricas.

---

## Alcance del POC
- 2–3 cultivos máximo.
- 1–2 mercados o regiones por cultivo.
- Frecuencia semanal.
- Horizonte de predicción: 1 a 4 semanas.
- Enfoque en simplicidad e interpretabilidad.

---

## Entregables
- `01_Datos_Raw.xlsx`: datos originales.
- `02_Dataset_Modelo.xlsx`: dataset limpio y variables.
- `03_Resultados_Pronostico.xlsx`: predicciones y métricas.
- `00_Resumen_Ejecutivo.xlsx`: conclusiones y recomendaciones.

---

## Requisitos
- Python 3.9+
- pandas
- numpy
- scikit-learn
- requests
- beautifulsoup4
- openpyxl

(opcional)
- selenium o playwright (solo si es necesario para scraping)

---

## Ejecución
Ejecutar pipeline completo:

```bash
python scripts/run_all.py
```
Ejecutar por etapas:

```bash
python scripts/run_extract.py
python scripts/run_transform.py
python scripts/run_model.py
```

## Limitaciones
- Inconsistencias en nombres y unidades entre fuentes.

- Diferente granularidad temporal (diario vs mensual vs anual).

- Posible fragilidad en scrapers si cambian las páginas.

- Modelos simples: no capturan completamente eventos extremos.