# Decisiones del proyecto

Registro ligero (estilo ADR) de las decisiones de arquitectura y de
producto que afectan al código. Una entrada nueva por cada decisión
relevante; nunca editar entradas antiguas — si una decisión queda
revertida, se crea una entrada nueva que la supere y se enlaza desde
la original.

> Los ADRs son inmutables una vez publicados. No se renombran ni renumeran;
> si una decisión se revierte o modifica, se añade un nuevo ADR que la
> supersede explícitamente.

## ADR-001: Modelo meteorológico único (2026-05-19)

> **Superado por ADR-005 (2026-05-20).** El modelo se cambió a ARPEGE
> tras descubrir que AROME France solo cubre ~60 h de horizonte y no
> sirve `freezing_level_height`.

**Decisión**: usar `meteofrance_arome_france` (1.3 km) como modelo único de v0.1.

**Contexto**: tras experimento `scripts/comparar_modelos.py`, todos los modelos
disponibles devuelven vientos en rango similar (factor 1.7-1.9) para el día de
prueba. AROME ofrece la mejor resolución con cobertura confirmada para ambas
zonas y dispone de `windgusts_10m` (ECMWF no).

**Alternativas consideradas**: `best_match`, `ecmwf_ifs025` (sin ráfagas),
`icon_eu` (resolución menor, 6.5 km), `meteofrance_arome_france_hd` (cobertura
más limitada y resolución 0.5 km).

**Limitación conocida**: `windspeed_10m` representa viento a 10 m sobre la
superficie del MDT del modelo, NO sobre cresta expuesta. En días activos el
viento real puede ser 1.5-2× el modelado. Recalibrar umbrales tras uso real
si los semáforos resultan sistemáticamente optimistas.

## ADR-002: Sin lógica de aludes propia (2026-05-19)

**Decisión**: en v0.1, enlazar a boletines oficiales (Lauegi, AEMET) y mostrar
aviso en cabecera. Nunca emitir predicción propia.

**Razón**: predicción de aludes es competencia técnica y legal específica.
Falsa precisión sería peligrosa para el usuario (yo).

## ADR-003: Estado adicional "SIN_DATOS" (2026-05-19)

**Decisión**: extender la enumeración del semáforo con un cuarto valor
`SIN_DATOS` (glifo ⚪) para días sin cobertura del modelo. Tres colores
canónicos siguen siendo VERDE / AMBAR / ROJO.

**Contexto**: AROME France tiene horizonte operativo de ~51 h. Con
`forecast_days=5` los días 3-5 vienen con todas las variables = `null`.
Sin un cuarto estado, `evaluar_dia` devolvería VERDE para esos días
porque ninguna regla dispara (NaN > umbral es False). Resultado:
semáforos verdes engañosos.

**Implementación**: si todas las agregaciones intentadas (no derivadas)
producen NaN para una fecha, el semáforo es `SIN_DATOS`. La spec original
de Semana 2 solo contemplaba tres estados; esto es una extensión defensiva.

**Reversibilidad**: si se decide en el futuro combinar AROME (días 1-2)
+ ARPEGE/ICON (días 3-5), este estado deja de ser necesario en la
práctica. El código y la enumeración pueden mantenerse para cubrir
otros casos de "sin datos" (fallos de fetch, variables faltantes en
todas las reglas) sin coste.

## ADR-004: Variables derivadas como avisos pendientes (2026-05-19)

**Decisión**: las reglas que referencian variables derivadas
(`snowfall_48h_previas`, `indice_tormenta`) declaradas en
`config/actividades.yaml` se saltan en Semana 2 y se emiten como
"Regla pendiente: …" en el campo `avisos` de la evaluación.

**Razón**: la lógica de derivación vive en `src/evaluar.py` y
`src/tormenta.py` (Semana 4). Queremos que la configuración pueda
declarar estas reglas desde ya sin romper el motor de evaluación.

**Consecuencia**: hasta Semana 4, ciertas actividades (skimo,
alpinismo_estival, trail, ciclismo) no tienen su semáforo de tormenta
funcional. El usuario lo ve como aviso textual, no como color.

**Nota (2026-05-20)**: `freezing_level_height` dejó esta categoría y se
calcula ya localmente (ver ADR-005). `snowfall_48h_previas` e
`indice_tormenta` siguen pendientes.

## ADR-005: Modelo único ARPEGE + cero térmico estimado (2026-05-20)

**Decisión**: revertir el plan de combinación AROME+ARPEGE. Usar
meteofrance_arpege_europe como modelo único de v0.1. Calcular
freezing_level_height aproximadamente desde temperature_2m y gradiente
adiabático estándar.

**Contexto**: ARPEGE cubre 111h (suficiente para 5 días). AROME añadiría
mejor resolución en horas 0-60 pero la diferencia práctica en viento es
~1 km/h. La combinación introduce complejidad arquitectónica (empalme
temporal, trazabilidad, lógica de discrepancia entre modelos) que no
compensa para v0.1 personal. Cero térmico no existe en ninguno de los
dos modelos Météo-France via Open-Meteo; se estima desde T2m con lapse
rate de 6.5 K/km, etiquetado como "estimado" en el output.

**Limitación conocida**: ARPEGE tiene resolución de ~25 km. Puede
subestimar viento en cresta vs un modelo de 1.3 km. Si tras uso real
los semáforos resultan sistemáticamente optimistas, evaluar en v0.2
override de AROME para variables de viento en horas 0-60.

**Limitación cero térmico**: FLH estimado por lapse rate; aproximación
de primer orden. Comparar con AEMET montaña en uso real; si discrepa
significativamente, añadir ECMWF como fuente secundaria solo de FLH
en v0.2.

**Variables descartadas del set requerido**: precipitation_probability
(no la usa ninguna regla en v0.1; no disponible en modelos
Météo-France).

## ADR-006: Índice de tormenta calculado localmente (2026-05-22)

**Decisión**: implementar índice de riesgo de tormenta 0-3 como variable
derivada local, basado en combinación de CAPE, weathercode WMO,
precipitación y humedad relativa.

**Contexto**: ARPEGE proporciona CAPE y weathercode pero no un índice
operativo de tormenta. El índice se construye con umbrales de literatura
meteorológica (CAPE < 500 estable; 500-1000 moderado; 1000-2000
significativo; > 2000 alto) modulados por confirmación del modelo
(weathercode 95/96/99) y por humedad relativa (atmósfera seca reduce
probabilidad de convección sostenida).

**Limitación conocida**: los umbrales de CAPE están calibrados para
latitudes medias en general, no específicamente para Pirineo. En uso
real (verano 2026) comparar con observaciones efectivas de tormenta
(rayos AEMET, observación directa) y recalibrar si hay sesgo
sistemático. La regla operativa "no estar arriba después de las 13:00
con tormenta probable" prima sobre el valor numérico exacto del índice.

**Alternativa no escogida**: usar `lifted_index` o `convective_inhibition`
si Open-Meteo los expusiera. Actualmente no están en el set público de
ARPEGE. Si se incorporan en v0.2, integrarlos.
