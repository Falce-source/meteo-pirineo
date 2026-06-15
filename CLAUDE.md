# CLAUDE.md — Contexto permanente de meteo-pirineo

> **AL EMPEZAR CADA SESIÓN: lee primero `ESTADO_TAREAS.md`.**
> Contiene el estado actual del repo y las tareas pendientes. Este
> archivo (`CLAUDE.md`) es el contexto estable; `ESTADO_TAREAS.md` es
> la foto operativa del momento.

## Qué es meteo-pirineo

Herramienta personal de pronóstico para actividades de montaña en el
Pirineo. Evalúa la idoneidad meteorológica de cada actividad (esquí de
montaña, alpinismo invernal, alpinismo estival, trail running, ciclismo)
en dos zonas del Pirineo central (Valle de Benasque y Vall d'Aran) a
cinco días vista, y devuelve un semáforo (verde/ámbar/rojo) por actividad
y día con los motivos del color a la vista.

Usuario único: Andrés. Es un proyecto personal y, a la vez, una credencial
técnica para su reorientación profesional hacia el espacio
naturaleza + datos + ciencia (nature-tech, meteo aplicada).

Sitio público: https://falce-source.github.io/meteo-pirineo/
Repositorio: https://github.com/Falce-source/meteo-pirineo

## Cómo funciona (arquitectura)

Pipeline diario, sin base de datos, sin login, sin backend:

1. **fetch** (`src/fetch.py`): consume la previsión horaria del modelo
   Météo-France ARPEGE (~25 km, 5 días) vía la API pública de Open-Meteo.
2. **derivadas** (`src/derivadas.py`): calcula variables que el modelo no
   da directamente: cero térmico (cota de nieve) por gradiente adiabático,
   e índice de riesgo de tormenta (0-3) desde CAPE, weathercode y
   precipitación.
3. **evaluar** (`src/evaluar.py`): aplica reglas declarativas (umbrales en
   YAML) por actividad. El peor componente determina el color. Calcula la
   mejor y peor ventana del día por actividad. Respeta la activación por
   temporada (cada actividad solo se evalúa en sus meses activos).
4. **render** (`src/render.py`): genera un HTML estático autocontenido,
   responsive, con detalle expandible por celda (motivos, datos clave,
   ventanas).
5. **main** (`src/main.py`): orquesta todo. Salida por consola + HTML.

La configuración vive en `config/`:
- `zonas.yaml`: zonas con coordenadas, elevación, boletín de aludes.
- `actividades.yaml`: actividades con umbrales declarativos, franja
  horaria, ventana mínima, meses activos.

Despliegue: GitHub Actions (`.github/workflows/update.yml`) ejecuta el
pipeline cada mañana (cron ~05-06 UTC, con latencia variable de GitHub),
regenera el HTML y lo publica en GitHub Pages.

## Stack

Python (pandas, requests, pyyaml, beautifulsoup4) + YAML declarativo +
GitHub Actions + GitHub Pages. Tests con pytest. Sin frameworks JS, sin
dependencias de pago.

## Principios del proyecto

- **Transparencia, no caja negra**: cada semáforo muestra los motivos que
  lo disparan. Nada se oculta.
- **No predice aludes**: enlaza a boletines oficiales (Lauegi, AEMET).
  Nunca emite predicción nivológica propia.
- **Honestidad sobre limitaciones**: lo que falta está documentado como
  deuda en el README y en los ADRs.
- **Sin sobreingeniería**: el valor es traducir previsiones profesionales
  en decisión operativa por actividad, no construir un modelo meteo propio.
- **Decisiones registradas**: las decisiones de arquitectura se documentan
  como ADRs en `docs/decisiones.md`.

## Convenciones de trabajo

- **Reglas en YAML, no en código**: los umbrales y la configuración de
  actividades/zonas se editan en `config/`, no en `src/`. Añadir una zona
  o ajustar un umbral no requiere tocar Python.
- **Tests acompañan cada cambio de lógica**: no se cambia `evaluar.py`,
  `derivadas.py` o `tormenta.py` sin tests que cubran el cambio.
- **`docs/index.html` es generado**: nunca se edita a mano. Ante conflicto
  de git, se regenera con `python -m src.main`.
- **ADRs son inmutables**: una vez publicado un ADR no se renombra ni
  renumera; si una decisión se revierte, se añade un ADR nuevo que la
  supersede.
- **Decisiones de dominio las toma Andrés** (umbrales, meses activos,
  qué actividad). **Decisiones de arquitectura** se proponen y se
  documentan como ADR.

## Cómo trabajamos (Andrés + asistente)

Andrés trabaja con un asistente que produce prompts autocontenidos para
Claude Code. Claude Code ejecuta en local; Andrés trae el reporte. El
asistente revisa, valida la plausibilidad física de los resultados, y
decide los siguientes pasos. Andrés toma las decisiones de dominio y
valida contra su experiencia real de montaña.

## Flujo git (importante: se trabaja desde dos ordenadores)

Este repo se trabaja desde dos máquinas (PC trabajo y PC personal), ambas
con la copia FUERA de OneDrive (en `C:\Users\afalceto\repos\meteo-pirineo`).

- **Al empezar una sesión**: `git pull --rebase origin main` (trae los
  commits automáticos del cron diario, que toca `docs/index.html`).
- **Al terminar una sesión**: commit + `git push`. No dejar trabajo sin
  pushear (causa divergencias con el cron y fricción en la otra máquina).
- **Conflictos en `docs/index.html`**: se resuelven regenerando con
  `python -m src.main --solo-html`, nunca editando a mano.
- El cron commitea a `main` a diario. Esto genera divergencia si se vuelve
  tras varios días sin pull. Es manejable con rebase.
