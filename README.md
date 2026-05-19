# meteo-pirineo

Herramienta personal de evaluación meteorológica para actividades de montaña en el Pirineo.

## Estado

**v0.1 en desarrollo.** Proyecto personal, un solo usuario.

| Semana | Alcance                                                                | Estado |
|--------|------------------------------------------------------------------------|--------|
| 1      | Bootstrap del repo, config de zonas/actividades, cliente Open-Meteo    | ✅      |
| 2      | Lógica de evaluación por actividad + orquestador + tabla por consola   | ✅      |
| 3      | Render HTML estático para GitHub Pages                                 | ⏳      |
| 4      | Índice de tormenta + GitHub Actions diario                             | ⏳      |

## Zonas y actividades

Zonas iniciales (puntos representativos en cota alta):

| ID         | Zona                                            | Macizo            | Elevación |
|------------|-------------------------------------------------|-------------------|-----------|
| `benasque` | Valle de Benasque (Cerler / bajo Aneto)         | Pirineo aragonés  | 2200 m    |
| `aran`     | Vall d'Aran (Baqueira / Port de la Bonaigua)    | Pirineo catalán   | 2070 m    |

Actividades evaluadas:

| ID                    | Actividad                          | Estación principal |
|-----------------------|------------------------------------|--------------------|
| `skimo`               | Esquí de montaña                   | Invierno           |
| `alpinismo_invierno`  | Alpinismo invernal / primaveral    | Invierno           |
| `alpinismo_estival`   | Alpinismo estival                  | Verano             |
| `trail`               | Trail running                      | Cualquiera         |
| `ciclismo`            | Ciclismo (carretera y MTB)         | Cualquiera         |

Umbrales y reglas en [`config/actividades.yaml`](config/actividades.yaml).

## Arquitectura

```
meteo-pirineo/
├── config/
│   ├── zonas.yaml         # Zonas de evaluación (coordenadas, elevación, boletín aludes)
│   └── actividades.yaml   # Actividades y umbrales (variable + agg + ámbar/rojo)
├── src/
│   ├── fetch.py           # Cliente Open-Meteo (5 días, horario, sin clave)
│   ├── evaluar.py         # Lógica pura: previsión + actividad -> semáforo + motivos
│   └── main.py            # Orquestador: fetch + evaluación + tabla por consola
├── scripts/               # Scripts puntuales de validación (no producción)
├── tests/
│   ├── test_fetch.py      # Tests del cliente con HTTP mockeado
│   ├── test_evaluar.py    # Tests de la lógica de evaluación con DataFrames sintéticos
│   └── fixtures/          # Respuesta real de Open-Meteo capturada en vivo
├── docs/
│   └── decisiones.md      # Decisiones de arquitectura (ADR ligero)
└── .github/workflows/     # CI/CD: actualización diaria (Semana 4)
```

## Fuente de datos

[Open-Meteo Forecast API](https://open-meteo.com/en/docs):

- Modelo `meteofrance_arome_france` (~1.3 km de resolución, ver `docs/decisiones.md`).
- Hasta 5 días de previsión horaria solicitados; el modelo entrega de forma fiable ~51 h (~2 días).
- Sin clave, sin coste, sin login.
- Timezone `Europe/Madrid`, viento en km/h.
- Variables horarias: temperatura, humedad, precipitación, probabilidad de precipitación, código meteo, nieve, nubosidad, viento medio y ráfaga a 10 m, dirección de viento, CAPE, altitud del cero térmico.

## Uso local

Requisitos: Python 3.10+.

```bash
# 1. Entorno virtual + dependencias
python -m venv .venv
source .venv/bin/activate     # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

# 2. Tabla de semáforos por zona (fetch + evaluación + render)
python -m src.main

# 3. Solo fetch crudo (tabla resumen por consola)
python -m src.fetch

# 4. Tests
pytest -v
```

La primera ejecución golpea la API en vivo. Las siguientes 24 h se sirven desde caché local (`.cache/openmeteo.sqlite`).

### Ejemplo de salida de `python -m src.main`

```
================================================================================
ZONA: Valle de Benasque (Cerler / bajo Aneto) — 42.65°N, 0.55°E, 2200 m
Última actualización: 2026-05-19 13:31 (modelo: meteofrance_arome_france)
================================================================================

Actividad                       19-may  20-may  21-may  22-may  23-may
------------------------------------------------------------------------
Esquí de montaña / Skimo        🟡      🟢      🟢      ⚪      ⚪
Alpinismo invernal / primaveral 🟡      🟢      🟢      ⚪      ⚪
Alpinismo estival               🟡      🟢      🟢      ⚪      ⚪
Trail running                   🟢      🟢      🟢      ⚪      ⚪
Ciclismo (carretera y MTB)      🟢      🟢      🟢      ⚪      ⚪

Avisos zona:
  - Consultar boletín de aludes oficial: AEMET - Pirineo aragonés …

Motivos del día más complicado (19-may):
  - Esquí de montaña / Skimo (AMBAR):
      · Nubosidad media en cota: 88.1 % (umbral ambar: 80 %)
      ⚠ Regla pendiente: Nevada reciente 48h (variable derivada no implementada)
  …
```

Glifos: 🟢 verde · 🟡 ámbar · 🔴 rojo · ⚪ sin datos (más allá del horizonte del modelo).

## Limitaciones conocidas

> **Modelo y viento en cota.** Los valores de `windspeed_10m` y `windgusts_10m` proceden del modelo Météo-France AROME (1.3 km de resolución) y representan el viento a 10 m sobre la superficie del modelo digital del terreno, no sobre una cumbre o cresta expuesta. En días sinópticamente activos, el viento real en cresta puede ser 1.5-2× el valor modelado. Los umbrales de las reglas están calibrados con experiencia personal en el Pirineo central; si tras uso real los semáforos resultan sistemáticamente optimistas en días de viento, conviene recalibrarlos a la baja.
>
> **Aludes.** Esta herramienta NO predice riesgo de aludes. Para condiciones nivológicas, consulta siempre el boletín oficial enlazado en cabecera (Lauegi para el Pirineo catalán, AEMET para el aragonés). La regla "Nevada reciente 48 h" en skimo solo dispara un aviso de "consultar boletín externo", nunca un semáforo verde sin reservas.

Limitaciones adicionales registradas:

- **Horizonte temporal AROME ≈ 51 h.** AROME France entrega de forma fiable los primeros ~2 días. A partir del día 3 las variables vienen vacías y el semáforo de esa fila aparece como ⚪ (sin datos). Si necesitas previsión a 5 días, cambiar de modelo o combinar varios (decisión pendiente, ver `docs/decisiones.md`).
- **`freezing_level_height` no disponible en AROME France.** La regla informativa de "cero térmico" en alpinismo se queda sin valor; el código no rompe pero esa fila no aporta.
- **Variables derivadas pendientes**: `snowfall_48h_previas` e `indice_tormenta` se declaran en `config/actividades.yaml` pero no se calculan hasta Semana 4. Las reglas que las usan emiten un aviso "Regla pendiente …".

## Aviso de aludes

**Este proyecto NO predice riesgo de aludes.** El sistema evalúa variables meteorológicas (viento, temperatura, precipitación, nubosidad) pero no realiza ninguna evaluación nivológica. Antes de cualquier salida invernal, consultar el boletín oficial:

- **Pirineo catalán (Aran):** [Lauegi (ICGC)](https://lauegi.report/)
- **Pirineo aragonés:** [AEMET — boletín de montaña](https://www.aemet.es/es/eltiempo/prediccion/montana?w=ag0)

## Licencia

MIT.
