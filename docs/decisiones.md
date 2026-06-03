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

## ADR-007: Mejor ventana del día como dato derivado (2026-05-20)

**Decisión**: añadir "mejor ventana del día" y "peor ventana del día" como
sub-evaluaciones derivadas mostradas en el modal de detalle. No cambiar la
unidad principal de evaluación (sigue siendo semáforo por día). El tamaño
de ventana es configurable por actividad en actividades.yaml mediante el
campo `ventana_minima_h`.

**Contexto**: feedback externo (ver docs/feedback_externo.md, Alicia) identificó
que la agregación a franja 07:00-17:00 oculta ventanas favorables dentro de
días con semáforo global AMBAR o ROJO. Para una actividad de 2-3h, el dato
operativo útil no es "el día es ámbar" sino "hay ventana de 3h VERDE entre
las 08:00 y las 11:00".

**Implementación**: ventana deslizante de paso 1h sobre la franja_horaria
de la actividad. Cada posición se evalúa con las mismas reglas que el día
completo. Se reporta la mejor y la peor sub-ventana.

**Limitación conocida**: la unidad principal sigue siendo "día". Una actividad
larga que cae justo en la transición entre una ventana favorable y una
desfavorable puede ser difícil de planificar con esta vista. La opción C
(rediseño a evaluación por franjas mañana/tarde como columnas separadas)
queda en ADR-008.

## ADR-008: Rediseño futuro a evaluación por franjas (horizonte) (2026-05-20)

**Decisión**: tras 2-4 semanas de uso real con la versión B (ADR-007),
re-evaluar si la herramienta debe rediseñarse a una unidad de evaluación
por franjas (mañana/tarde como columnas separadas, o granularidad mayor).

**Contexto**: el feedback externo y la naturaleza de las actividades de
montaña sugieren que "un semáforo por día" puede ser excesivamente
agregado. ADR-007 mitiga el problema con dato derivado en el modal,
pero no cambia la unidad principal. Esta decisión queda pendiente de
datos de uso real.

**Criterios para tomar la decisión**:
- Si en uso real las "mejores ventanas" del modal son consistentemente
  diferentes del semáforo global, indica que la unidad "día" engaña y
  procede rediseño.
- Si las ventanas suelen coincidir con el semáforo global (días
  meteorológicamente homogéneos), el rediseño no añade valor.

**Datos a recopilar**: en docs/uso_real.md, anotar para cada salida:
fecha, zona, actividad, semáforo global, mejor ventana, peor ventana,
qué se encontró realmente.

## ADR-009: Algoritmo de ventanas — opción 3 con desempate por menor solape (2026-06-02)

**Decisión**: el algoritmo de "mejor y peor ventana del día" muestra una
sola ventana si todas las sub-ventanas tienen el mismo semáforo
("homogéneo"); y muestra mejor + peor solo cuando existe diferenciación
semafórica entre sub-ventanas. En caso de múltiples sub-ventanas con el
mismo semáforo candidato a "mejor" o "peor", se aplica desempate por
menor solape temporal con la otra ventana seleccionada.

**Contexto**: la implementación inicial de Semana 5 (ADR-007) producía
ventanas con solapamiento alto (p.ej. mejor 07-13 AMBAR y peor 09-15 ROJO
con 4h en común sobre 6h totales). La información semafórica era correcta
pero el solapamiento hacía el output visualmente confuso para el usuario.

**Implementación**: enumerar todas las sub-ventanas, identificar candidatas
de mejor y peor semáforo, elegir el par que minimiza el solape temporal.
En empate, preferir el par más temprano en el día.

**Limitación**: cuando solo existe una sub-ventana posible para "mejor" y
otra para "peor", y ambas solapan forzosamente, se devuelven igualmente.
El usuario ve dos rangos con solape pero distinguidos semafóricamente.
Este caso es inevitable y aceptable.

## ADR-010: Activación de actividades por mes calendario (2026-06-02)

**Decisión**: cada actividad declara una lista `meses_activos: [int]` en
config/actividades.yaml. La evaluación devuelve None para combinaciones
(actividad, día) en meses no activos. El render omite la fila completa
si la actividad no está activa en ningún día del horizonte, y muestra
celda placeholder gris si está activa en algunos días pero no en otros.

**Contexto**: previo a este ADR, skimo se evaluaba en agosto y alpinismo
invernal en julio, produciendo semáforos sin sentido operativo. Es un
fallo visible para cualquier usuario externo que abriera la app fuera
de temporada típica de cada deporte.

**Tabla de meses activos en v0.1**:
- skimo: nov-may
- alpinismo invernal/primaveral: nov-jun
- alpinismo estival: jun-oct
- trail: mar-nov
- ciclismo: mar-nov

**Granularidad**: por mes calendario completo. Decisión consciente
para mantener simplicidad. Si en uso real se observa que los bordes
de transición (ej. principio o final de junio para skimo) generan
ruido, evaluar en futuro paso a rangos de fechas configurables.

**Limitación conocida**: trail y ciclismo en pleno invierno no se
evalúan aunque hay practicantes que sí lo hacen. Decisión deliberada
de Andrés. Si en uso real falta, mover umbrales en YAML (no requiere
cambio de código).
