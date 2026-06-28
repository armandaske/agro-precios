# Guia detallada de analisis

Este documento describe en detalle las tres lineas analiticas del repositorio, como se construyen, como se ejecutan, que significan sus salidas y cuales son sus principales limitaciones. El objetivo es que sirva como guia operativa y como material de apoyo para demos internas o conversaciones con negocio.

## 1. Vision general

El repositorio tiene cuatro capas logicas:

1. Extraccion de datos publicos y comerciales.
2. Normalizacion y consolidacion en workbooks y parquet.
3. Feature engineering con validacion temporal.
4. Reportes operativos y artefactos de modelo.

Las tres analiticas actuales son:

- `riesgo_hidrico`: monitoreo y pronostico por presa usando cortes por decena.
- `nowcast_produccion`: estimacion de produccion por cultivo y estado usando Avance Agricola y, cuando existe historial etiquetado suficiente, Cierre Agricola.
- `alerta_precios`: pronostico de precios por producto y mercado a partir de SNIIM, spreads retail-mayoreo y contexto productivo/hidrico.

La filosofia del repo es conservadora:

- Se usan cortes temporales reales, no random split.
- Un modelo candidato no se presenta como operativo si no supera baselines simples fuera de muestra.
- La ausencia de datos suficientes no se maquilla; en ese caso se usa un baseline y se declara la limitacion.

## 2. Fuentes de datos y papel de cada una

### SNIIM

Rol:
- Fuente principal para precios mayoristas diarios de frutas y hortalizas.

Uso analitico:
- Alimenta el panel diario de precios.
- Es la base del pipeline `alerta_precios`.

Limitaciones:
- Puede haber dias sin registros.
- El nombre real del producto puede variar respecto al producto canonico configurado.
- Cambios en HTML o en el flujo del portal pueden romper el extractor.

### Walmart y Chedraui

Rol:
- Referencia retail para estimar spreads contra mayoreo.

Uso analitico:
- En `alerta_precios` se usan `precio_walmart`, `precio_chedraui`, `spread_walmart` y `spread_chedraui`.
- Tambien sirven para identificar anomalías de margen retail-mayoreo.

Limitaciones:
- Los precios pueden ser snapshots de pagina, no necesariamente transacciones efectivas.
- La inferencia por kg depende de la presentacion detectada.
- Los buscadores pueden devolver productos cercanos pero no equivalentes si la configuracion no es estricta.

### Presas Agricolas

Rol:
- Fuente base para almacenamiento, capacidad y trayectoria de presas por decena.

Uso analitico:
- Alimenta `riesgo_hidrico`.
- El agregado estatal resultante se usa como contexto opcional en `alerta_precios` y `nowcast_produccion`.

Limitaciones:
- La frecuencia es por decena, no diaria.
- El estado de una presa no siempre captura toda la complejidad hidrologica de un cultivo o region.
- El modelo no infiere causalidad; mide relacion predictiva sobre el historial disponible.

### SIAP Avance Agricola

Rol:
- Fuente mensual acumulada por cultivo y entidad.

Uso analitico:
- Contexto agricola mensual en el workbook maestro.
- Base del `nowcast_produccion`.
- Input opcional para `alerta_precios`.

Limitaciones:
- La calidad del nowcast depende de que existan suficientes cortes historicos emparejables con Cierre Agricola.
- El corte mensual es acumulado, no una foto puntual de todo el ciclo productivo final.

### SIAP Cierre Agricola

Rol:
- Referencia anual final por cultivo y entidad.

Uso analitico:
- Etiquetas historicas para entrenar `nowcast_produccion`, cuando hay suficiente superposicion temporal.
- PMR anual secundario en el workbook maestro.

Limitaciones:
- El PMR anual puede estar en unidades no directamente comparables con precios por kg de otras fuentes.
- La cobertura historica disponible en este repo todavia es insuficiente para algunos entrenamientos defendibles.

### NASA POWER

Rol:
- Enriquecimiento climatico opcional para presas.

Uso analitico:
- Solo entra a `riesgo_hidrico` si se pasa explicitamente `--climate-file`.
- Luego ese contexto puede propagarse indirectamente a otros pipelines via `state_decena_features.parquet`.

Limitaciones:
- No se usa por default.
- Si no pasas `--climate-file`, la corrida ocurre sin clima.
- La llave correcta es `id_conagua + fecha`.

### Precios internacionales publicos

Rol:
- Contexto externo opcional para commodities, tipo de cambio y mercados relacionados.

Uso analitico:
- Se materializan en `data/analysis/international_prices/international_price_features.parquet`.
- El workbook maestro los muestra en `precios_internacionales`, `cobertura_internacional` y `mapa_proxies`.
- `alerta_precios` los usa solo si se pasa `--international-features`.

Limitaciones:
- Esta v1 no usa API keys, tokens ni feeds pagados.
- Los proxies `diagnostico_only` no entran al modelo.
- Un proxy debil no debe presentarse como driver causal.
- Los joins usan `fecha_disponible`, no la fecha economica cruda, para evitar fuga de informacion futura.

## 3. Workbook maestro comparativo

Archivo:
- `data/analysis/master_price_workbook.xlsx`

Objetivo:
- Reunir en una sola pieza de trabajo el panel diario de precios, el contexto agricola mensual, la referencia anual de Cierre y el contexto internacional opcional.

Hojas principales:

- `panel_daily_long`: tabla larga por fuente.
- `compare_daily_wide`: tabla ancha para analisis por producto-fecha.
- `sniim_daily_stats`: agregados diarios de SNIIM.
- `avance_monthly_stats`: agregados mensuales nacionales desde Avance.
- `avance_entity_monthly`: detalle por entidad.
- `cierre_annual_stats`: PMR anual ponderado por produccion.
- `precios_internacionales`: proxies internacionales normalizados.
- `cobertura_internacional`: disponibilidad de proxies por fecha y producto.
- `mapa_proxies`: mapeo de cada producto canonico a sus proxies.
- `coverage`: cobertura general por fuente.

Lectura recomendada en demo:

1. Mostrar `compare_daily_wide` para explicar la convergencia de fuentes.
2. Mostrar `coverage` para hablar de cobertura y vacios.
3. Mostrar `precios_internacionales` y `mapa_proxies` para explicar el contexto externo.

Limitaciones:

- No todas las fuentes tienen la misma frecuencia.
- Avance es mensual y se injerta sobre filas diarias del mismo mes.
- Cierre es anual y sirve mas como referencia que como precio diario comparable.

## 4. Riesgo hidrico

Entrypoint:
- `python -m scripts.run_water_risk_model`

Inputs principales:

- `data/raw/presas_agricolas/*.xlsx`
- Opcional: `data/raw/climate/nasa_power_decena.parquet`

Artefactos principales:

- `data/analysis/water_risk/dam_decena_features.parquet`
- `data/analysis/water_risk/state_decena_features.parquet`
- `data/analysis/water_risk/alertas_riesgo_hidrico.csv`
- `data/analysis/water_risk/monitoreo_riesgo_hidrico.xlsx`
- `data/analysis/water_risk/monitoreo_riesgo_hidrico.html`
- `data/analysis/water_risk/metricas_riesgo_hidrico.json`

### Como funciona

Unidad de tiempo:
- La presa se observa por decena.

Horizontes:
- Por default usa `3, 6, 9` decenas.
- Eso equivale a `30, 60 y 90 dias`.

Features:
- Lags de almacenamiento.
- Cambios recientes por decena.
- Promedios y desviaciones moviles.
- Estacionalidad por mes y por decena del anio.
- Variables climaticas opcionales si se pasan explicitamente.

Baselines:
- `decena_anterior`
- `misma_decena_anio_anterior`
- `promedio_3_decenas`
- `delta_estacional_mediana`

Modelos candidatos:
- `xgboost_nivel`: pronostica el porcentaje futuro directamente.
- `xgboost_delta`: pronostica el cambio esperado respecto al valor actual y luego reconstruye el porcentaje futuro.

Gobernanza:
- XGBoost solo queda operativo si mejora el MAE fuera de muestra.
- Si no lo hace, el pronostico operativo usa el mejor baseline.

Modo demo forzado:
- Puedes forzar `xgboost_nivel`, `xgboost_delta`, `decena_anterior`, `misma_decena_anio_anterior`, `promedio_3_decenas` o `delta_estacional_mediana` con `--force-model`.
- Si lo haces, el pipeline deja trazabilidad explicita en metricas, CSV/XLSX y HTML.
- Ese modo no debe presentarse como seleccion operativa validada; es una sobrescritura manual.

### Como leer la salida

En `alertas_riesgo_hidrico.csv`:

- `porcentaje_almacenamiento`: valor actual.
- `porcentaje_pronosticado`: valor esperado al horizonte.
- `delta_pronosticado_puntos`: diferencia esperada en puntos porcentuales frente al valor actual.
- `metodo_pronostico`: metodo que quedo operativo en ese horizonte.
- `pronostico_es_persistencia`: marca cuando el horizonte quedo en baseline de continuidad.
- `probabilidad_bajo_40`, `probabilidad_bajo_25`, `probabilidad_bajo_15`: riesgo de caer debajo de umbrales operativos.
- `nivel_riesgo`: clasificacion final.
- `horizonte_dias`: 30, 60 o 90 dias.

En `monitoreo_riesgo_hidrico.html`:

- El tablero ahora separa claramente los horizontes por pestaña.
- Hay una tabla resumen por horizonte.
- Cada mapa se renderiza por horizonte, no solo por el mas corto.
- El HTML muestra el metodo operativo y el cambio esperado; si un horizonte queda en persistencia, lo explica explicitamente.
- La tabla HTML lista todas las presas evaluadas en cada horizonte; ya no se limita a un top corto.

### Limitaciones clave

- El modelo no estima lluvia futura si no se le entrega clima externo.
- Incluso con clima externo, el uso operativo debe quedar supeditado al backtesting; no se asume que NASA POWER mejore todos los horizontes.
- Una presa no equivale automaticamente al estres hidrico de todos los cultivos cercanos.
- A mayor horizonte, suele deteriorarse el error; por eso se reportan 30, 60 y 90 dias por separado.

## 5. Nowcast de produccion

Entrypoint:
- `python -m scripts.run_production_nowcast`

Inputs principales:

- `data/raw/avance_agricola_batch/`
- `data/raw/cierre_agricola_batch/`
- Opcional: `data/analysis/water_risk/state_decena_features.parquet`

Artefactos principales:

- `data/analysis/production_nowcast/crop_state_cutoff_features.parquet`
- `data/analysis/production_nowcast/pronostico_produccion_mensual.csv`
- `data/analysis/production_nowcast/nowcast_produccion_agricola.xlsx`
- `data/analysis/production_nowcast/reporte_nowcast_produccion.html`
- `data/analysis/production_nowcast/principales_riesgos_produccion.png`
- `data/analysis/production_nowcast/metricas_nowcast_produccion.json`

### Como funciona

Unidad analitica:
- cultivo + estado + corte mensual

Objetivo:
- Estimar produccion final del ciclo usando informacion acumulada parcial.

Horizonte del pronostico:
- El nowcast no pronostica "los proximos 7, 14 o 30 dias".
- El objetivo es la `produccion_final` del mismo anio agricola para ese cultivo y estado.
- En otras palabras: toma el ultimo corte mensual disponible y estima con cuanto cerrara el anio o ciclo agricola cuando se observe el resultado final.

Modo de operacion:

- `xgboost` cuando hay suficientes etiquetas historicas.
- `base_historica` cuando no las hay.

Regla defensiva:
- Si hay menos de 100 cortes etiquetados o menos de 2 anios etiquetados, no entrena modelo operativo.

### Como leer la salida

Campos utiles:

- `produccion_pronosticada`
- `produccion_p10`
- `produccion_p90`
- `referencia_comparacion`, `tipo_referencia_comparacion`, `cambio_pct_vs_referencia`
- `probabilidad_caida_10`, `probabilidad_caida_15`, `probabilidad_caida_20`
- `escenario_normal`, `escenario_seco`, `escenario_sequia_severa`

Definicion explicita:

- `produccion_pronosticada`:
  es la mejor estimacion puntual de la produccion final esperada para ese cultivo y estado en el cierre del mismo anio agricola, usando la informacion disponible al corte actual. Es el numero central del pronostico.
- `produccion_p10`:
  es una banda inferior orientativa para la produccion final. Debe leerse como un escenario pesimista razonable dentro del rango del sistema, no como "el peor caso posible".
- `produccion_p90`:
  es una banda superior orientativa para la produccion final. Debe leerse como un escenario optimista razonable dentro del rango del sistema, no como una garantia de techo.
- `referencia_comparacion`:
  volumen historico usado para contextualizar el pronostico. Prefiere el `anio anterior` y, si no existe, cae al `promedio 5 anios`.
- `tipo_referencia_comparacion`:
  indica si la comparacion visible usa `anio_anterior`, `promedio_5_anios` o queda `sin_referencia`.
- `cambio_pct_vs_referencia`:
  variacion porcentual esperada del pronostico central contra esa referencia visible. Un `-12%` significa que el sistema espera cerrar 12% abajo de esa base.
- `probabilidad_caida_10`:
  probabilidad estimada de que la produccion final quede 10% o mas abajo del anio anterior.
- `probabilidad_caida_15`:
  probabilidad estimada de que la produccion final quede 15% o mas abajo del anio anterior.
- `probabilidad_caida_20`:
  probabilidad estimada de que la produccion final quede 20% o mas abajo del anio anterior.
- `escenario_normal`:
  el pronostico central sin ajuste adicional.
- `escenario_seco`:
  una version del pronostico central castigada con un supuesto de sequedad de `-8%`.
- `escenario_sequia_severa`:
  una version del pronostico central castigada con un supuesto de sequia severa de `-15%`.

Como leerlo en negocio:

- Si `produccion_pronosticada` es alta pero `produccion_p10` queda mucho mas abajo, el volumen central puede verse bien pero la incertidumbre es amplia.
- Si `probabilidad_caida_10` o `probabilidad_caida_15` es alta, la señal importante no es solo el volumen esperado sino el riesgo de decepcion productiva frente al anio previo.
- Si `produccion_pronosticada` y `produccion_p10` estan relativamente cerca, la estimacion es mas estable.
- Si `cambio_pct_vs_referencia` es negativo, ya tienes una medida directa de la magnitud de la caida y no solo un volumen absoluto.

Ejemplo practico:

- `produccion_pronosticada = 100000`
- `produccion_p10 = 90000`
- `produccion_p90 = 112000`
- `probabilidad_caida_10 = 0.65`

Lectura:

- el escenario central es `100000`
- un rango razonable del sistema va aproximadamente de `90000` a `112000`
- ademas, el sistema estima `65%` de probabilidad de terminar `10%` o mas abajo del anio anterior
- ese resultado se refiere al cierre final del mismo anio agricola, no al siguiente mes inmediato

Interpretacion:
- Los escenarios secos no son un hallazgo causal; son supuestos explicitos sobre el pronostico central.
- `p10` y `p90` no son garantias ni limites fisicos; son bandas orientativas construidas a partir del comportamiento historico del error del sistema.

Vista demo recomendada:
- `reporte_nowcast_produccion.html` resume modo, volumen esperado, riesgos principales y volumenes mas relevantes, mostrando tambien la base de comparacion y la variacion esperada.
- `principales_riesgos_produccion.png` sirve para una diapositiva o resumen rapido.

### Limitaciones clave

- Hoy la principal limitacion del repo es historica: no hay suficiente traslape Avance/Cierre etiquetado por mismo cultivo, estado y anio para varios casos.
- Por eso el nowcast puede quedar en `base_historica` aunque el pipeline corra correctamente.

## 6. Alerta temprana de precios

Entrypoint:
- `python -m scripts.run_price_shock_model`

Inputs principales:

- `data/daily_runs/`
- Opcional: `data/analysis/production_nowcast/pronostico_produccion_mensual.csv`
- Opcional: `data/analysis/water_risk/state_decena_features.parquet`
- Opcional: `data/analysis/international_prices/international_price_features.parquet`

Artefactos principales:

- `data/analysis/price_shock/price_product_market_daily_features.parquet`
- `data/analysis/price_shock/alertas_semanales_precios.csv`
- `data/analysis/price_shock/anomalias_margen_retail.csv`
- `data/analysis/price_shock/alerta_temprana_precios.xlsx`
- `data/analysis/price_shock/reporte_alertas_precios.html`
- `data/analysis/price_shock/metricas_modelo_precios.json`
- `data/analysis/price_shock/principales_alertas_precios.png`
- `data/analysis/price_shock/principales_alertas_precios_h7.png`
- `data/analysis/price_shock/principales_alertas_precios_h14.png`
- `data/analysis/price_shock/principales_alertas_precios_h28.png`

### Como funciona

Unidad analitica:
- producto + mercado + fecha

Horizontes por default:
- `7, 14 y 28 dias`

Features:
- Lags de precio.
- Promedios y volatilidad.
- Estacionalidad.
- Spreads retail-mayoreo.
- Contexto hidrico nacional.
- Contexto productivo agregado.
- Contexto internacional opcional si existe y esta marcado como `feature`.

Baselines:
- `autorregresivo`
- `estacional_7_dias`

Gobernanza:
- El metodo operativo por horizonte es el de menor MAE fuera de muestra.

### Como leer la salida

Campos utiles:

- `precio_actual`
- `precio_pronosticado`
- `precio_p10`
- `precio_p90`
- `probabilidad_alza_10`
- `probabilidad_alza_15`
- `nivel_alerta`
- `accion_sugerida`
- `metodo_pronostico`

Definicion explicita:

- `precio_actual`:
  ultimo precio observado que el sistema toma como base para ese producto y mercado.
- `precio_pronosticado`:
  mejor estimacion puntual del precio al horizonte indicado.
- `precio_p10`:
  banda inferior orientativa del precio esperado al horizonte. Debe leerse como un escenario relativamente bajo dentro del rango normal del sistema.
- `precio_p90`:
  banda superior orientativa del precio esperado al horizonte. Debe leerse como un escenario relativamente alto dentro del rango normal del sistema.
- `probabilidad_alza_10`:
  probabilidad estimada de que el precio suba al menos 10% respecto al precio actual.
- `probabilidad_alza_15`:
  probabilidad estimada de que el precio suba al menos 15% respecto al precio actual.
- `nivel_alerta`:
  clasificacion agregada del riesgo comercial derivada de la probabilidad de alza.
- `accion_sugerida`:
  recomendacion comercial simple para lectura rapida.
- `metodo_pronostico`:
  metodo que quedo operativo para ese horizonte segun el menor MAE fuera de muestra, salvo que se haya forzado manualmente un modo demo.

Como leerlo en negocio:

- Si `precio_pronosticado` ya esta bastante arriba de `precio_actual`, el sesgo central es alcista.
- Si `precio_p90` se aleja mucho del central, hay una cola de riesgo al alza importante.
- Si `probabilidad_alza_10` es alta, la implicacion no es teorica: hay una señal concreta para compras, cobertura o monitoreo intensivo.

Ejemplo practico:

- `precio_actual = 40`
- `precio_pronosticado = 47`
- `precio_p10 = 42`
- `precio_p90 = 55`
- `probabilidad_alza_10 = 0.82`

Lectura:

- el precio central esperado es `47`
- el sistema ve un rango razonable entre `42` y `55`
- ademas, estima `82%` de probabilidad de que el precio suba al menos `10%` frente al actual

En `anomalias_margen_retail.csv`:

- `spread_retail_mayoreo`
- `puntaje_anomalia`

Sirve para detectar:
- Desacoples entre retail y mayoreo.
- Posibles ventanas comerciales o señales de tension de mercado.

Vista demo recomendada:
- El HTML ahora separa visualmente cada horizonte en lugar de mezclar 7, 14 y 28 dias en una sola tabla principal.
- El workbook incluye `resumen_horizontes` para lectura ejecutiva rapida.

### Limitaciones clave

- Los resultados son predictivos, no causales.
- Los spreads dependen de la calidad de matching retail.
- Si no hay proxies internacionales `feature` disponibles, el pipeline sigue funcionando sin ellos.
- Los proxies `diagnostico_only` no cambian el modelo, solo el contexto analitico.

## 7. Precios internacionales publicos

Entrypoints:

- `python -m scripts.fetch_public_international_prices`
- `python -m scripts.build_international_price_features`

Objetivo:
- Agregar contexto externo sin depender de credenciales.

Flujo:

1. Descargar World Bank Pink Sheet y FRED si responde.
2. Colocar manualmente archivos publicos de USDA AMS e IMF si se necesitan.
3. Construir el parquet normalizado.
4. Pasarlo al workbook maestro y a `alerta_precios`.

Claves del diseño:

- `uso_modelo = feature`: puede entrar al modelo.
- `uso_modelo = diagnostico_only`: solo aparece en contexto analitico.
- `fecha_disponible`: fecha real desde la que se permite usar el dato en joins.

Limitaciones clave:

- Si FRED falla o USDA/IMF no estan cargados manualmente, la capa internacional puede quedar parcial.
- En ese escenario, la demo sigue siendo valida si se presenta como contexto parcial y no como enrichment completo.

## 8. Comandos recomendados

### Correr toda la historia analitica

```powershell
python -m scripts.run_analysis_pipeline
```

### Correr con NASA POWER

```powershell
python -m scripts.run_analysis_pipeline `
  --climate-file data/raw/climate/nasa_power_decena.parquet
```

### Correr con precios internacionales

```powershell
python -m scripts.run_analysis_pipeline `
  --international-features data/analysis/international_prices/international_price_features.parquet
```

### Correr con ambas capas opcionales

```powershell
python -m scripts.run_analysis_pipeline `
  --climate-file data/raw/climate/nasa_power_decena.parquet `
  --international-features data/analysis/international_prices/international_price_features.parquet
```

### Cambiar horizontes de riesgo hidrico

```powershell
python -m scripts.run_water_risk_model --horizons 1 3 6
python -m scripts.run_water_risk_model --horizons 2 4 8
```

### Reforzar el historico nacional de presas

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_presas_historical_backfill --start-year 1999 --end-year 2026
```

### Forzar metodo de riesgo hidrico para demo

```powershell
python -m scripts.run_water_risk_model --force-model xgboost_delta
python -m scripts.run_water_risk_model --force-model decena_anterior
```

Nota:
- Los valores se expresan en decenas. Internamente `3 = 30 dias`, `6 = 60 dias`, `9 = 90 dias`, etc.

## 9. Guion recomendado para demo

1. Abrir `data/analysis/master_price_workbook.xlsx`.
2. Mostrar `compare_daily_wide` para explicar consolidacion de fuentes.
3. Mostrar `coverage` para explicar donde hay cobertura y donde no.
4. Mostrar `precios_internacionales` y `mapa_proxies` para explicar el enrichment externo.
5. Abrir `data/analysis/price_shock/reporte_alertas_precios.html`.
6. Abrir `data/analysis/water_risk/monitoreo_riesgo_hidrico.html` y cambiar entre 30, 60 y 90 dias.
7. Explicar que `nowcast_produccion` hoy corre en baseline historico por limitacion de etiquetado, no por falla tecnica.

## 10. Riesgos de interpretacion

No deberias presentar como hecho:

- Que un proxy internacional debil explica causalmente un precio local.
- Que el nowcast actual esta entrenado si el reporte dice `base_historica`.
- Que NASA POWER se uso si no se paso `--climate-file`.
- Que el PMR anual de Cierre es directamente comparable con un precio diario por kg.

Si necesitas una formulacion ejecutiva defensible:

- "El sistema ya integra extraccion, panel comparativo y alertas temporales con gobernanza de baseline. Algunas capas opcionales, como clima NASA o proxies internacionales mas ricos, dependen de disponibilidad adicional de datos y se activan sin cambiar la arquitectura del pipeline."
