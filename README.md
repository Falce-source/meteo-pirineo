# meteo-pirineo

Herramienta personal de evaluación meteorológica para actividades de montaña en el Pirineo.

## Estado

**v0.1 en desarrollo.** Proyecto personal, un solo usuario.

| Semana | Alcance                                                                | Estado |
|--------|------------------------------------------------------------------------|--------|
| 1      | Bootstrap del repo, config de zonas/actividades, cliente Open-Meteo    | ✅      |
| 2      | Lógica de evaluación por actividad (umbrales → ámbar/rojo)             | ⏳      |
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
│   └── fetch.py           # Cliente Open-Meteo (5 días, horario, sin clave)
├── tests/
│   ├── test_fetch.py      # Tests del cliente con HTTP mockeado
│   └── fixtures/          # Respuesta real de Open-Meteo capturada en vivo
├── docs/                  # Salida HTML estática (Semana 3)
└── .github/workflows/     # CI/CD: actualización diaria (Semana 4)
```

## Fuente de datos

[Open-Meteo Forecast API](https://open-meteo.com/en/docs):

- Modelo `best_match` (el agregador escoge el mejor modelo por zona).
- 5 días de previsión horaria.
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

# 2. Fetch de prueba contra Open-Meteo (imprime tabla resumen)
python -m src.fetch

# 3. Tests
pytest -v
```

La primera ejecución de `python -m src.fetch` golpea la API en vivo. Las siguientes 24 h se sirven desde caché local (`.cache/openmeteo.sqlite`).

## Aviso de aludes

**Este proyecto NO predice riesgo de aludes.** El sistema evalúa variables meteorológicas (viento, temperatura, precipitación, nubosidad) pero no realiza ninguna evaluación nivológica. Antes de cualquier salida invernal, consultar el boletín oficial:

- **Pirineo catalán (Aran):** [Lauegi (ICGC)](https://lauegi.report/)
- **Pirineo aragonés:** [AEMET — boletín de montaña](https://www.aemet.es/es/eltiempo/prediccion/montana?w=ag0)

La columna "nevada reciente 48h" que aparece en la actividad skimo es informativa y solo indica que se ha producido una nevada relevante; en ningún caso sustituye la lectura del boletín.

## Licencia

MIT.
