# Material de comunicación — meteo-pirineo

Piezas reutilizables para LinkedIn, mensajes a contactos profesionales,
y referencias al proyecto. Cada pieza en español e inglés. Copia-pega
directo, sin edición salvo personalización del destinatario en mensajes.

URLs canónicas:
- Sitio: https://falce-source.github.io/meteo-pirineo/
- Repositorio: https://github.com/Falce-source/meteo-pirineo

Capturas disponibles en `docs/img/`:
- `captura_01_vista_general.png`: tabla completa escritorio.
- `captura_02_vista_movil_cabecera.png`: vista móvil cabecera.
- `captura_03_vista_movil_tabla.png`: vista móvil tabla.
- `captura_04_modal_ventana.png`: modal detalle con ventana de oportunidad.

Última actualización del material: 2026-06-02.

---

## Pieza 1 — Pitch corto (4-6 líneas)

Uso: bio LinkedIn, respuesta rápida a "¿en qué estás trabajando?",
intro a contactos.

### Español

meteo-pirineo es una herramienta personal para evaluar idoneidad meteorológica de actividades de montaña en el Pirineo. El enfoque es deliberado: traducir conocimiento de dominio en decisión operativa reproducible. Codifica criterio experto en reglas trazables sobre la previsión horaria de un modelo meteorológico profesional, y la salida no son datos crudos sino un semáforo por actividad y día, con los motivos del color y la mejor y peor ventana dentro de la franja útil. Cubre esquí de montaña, alpinismo invernal y estival, trail y ciclismo, en dos zonas del Pirineo central.

### English

meteo-pirineo is a personal tool for evaluating weather suitability of mountain activities in the Pyrenees. The approach is deliberate: translating domain knowledge into reproducible operational decisions. It encodes expert judgement as traceable rules over hourly forecasts from a professional weather model, and the output is not raw data but a traffic-light verdict per activity per day, together with the reasons for the colour and the best and worst window within the active timeframe. It covers ski touring, winter and summer alpinism, trail running and cycling, across two zones in the central Pyrenees.

---

## Pieza 2 — Descripción técnica (4-6 líneas)

Uso: perfil técnico, README, contexto para evaluador con criterio
de ingeniería.

### Español

Stack: Python (pandas, requests, pyyaml), GitHub Actions y GitHub Pages. Fuente: API pública de Open-Meteo sirviendo el modelo Météo-France ARPEGE (~25 km, 5 días). Pipeline diario: fetch, enriquecimiento con variables derivadas (cero térmico por gradiente adiabático, índice de tormenta desde CAPE y códigos WMO), evaluación por reglas declarativas en YAML, render HTML estático autocontenido. Cubre 2 zonas y 5 actividades, con ventanas óptimas por actividad calculadas mediante deslizante de paso horario. Cobertura: 50 tests unitarios, 9 decisiones de arquitectura documentadas (ADRs), cron diario y despliegue continuo. Desarrollo iterativo con asistente de IA y validación contra observación real.

### English

Stack: Python (pandas, requests, pyyaml), GitHub Actions and GitHub Pages. Source: the public Open-Meteo API serving the Météo-France ARPEGE model (~25 km, 5-day horizon). Daily pipeline: fetch, enrichment with derived variables (freezing level via lapse rate, storm index from CAPE and WMO weather codes), rule-based evaluation declared in YAML, self-contained static HTML render. Covers 2 zones and 5 activities, with optimal time windows per activity computed by hourly-step sliding evaluation. Coverage: 50 unit tests, 9 documented architecture decisions (ADRs), daily cron and continuous deployment. Iterative development with an AI assistant and validation against real observation.

---

## Pieza 3 — Por qué (1 párrafo, 6-10 líneas)

Uso: motivación y caso de uso real. Incluye referencia a Maladeta
como ejemplo concreto.

### Español

Las apps meteorológicas estándar entregan datos: temperatura, viento, precipitación, nubosidad, ráfagas, cero térmico. Para una salida concreta —por ejemplo, subir a la Maladeta en esquís a primera hora— la decisión "voy / no voy" depende de cruzar ocho o diez de esas variables a la vez con un criterio específico: viento medio manejable en cresta, cero térmico suficientemente alto para que la nieve no esté podrida, ausencia de tormenta vespertina probable, nubosidad baja para orientarse en zona glaciar, ráfagas tolerables en el filo. Ese cruce existe en la cabeza del montañero con experiencia; no en ninguna pantalla. La herramienta lo formaliza: los umbrales son los míos, las reglas viven en un archivo YAML legible, y el semáforo se acompaña siempre de los motivos que lo disparan. La salida que ve el usuario no oculta los criterios que la generan; cada color es auditable y se puede recalibrar. El enfoque —codificar criterio experto como reglas auditables sobre datos de modelo— es transferible a otros contextos de decisión operativa basada en datos: agricultura, energía rural, gestión territorial.

### English

Standard weather apps deliver data: temperature, wind, precipitation, cloud cover, gusts, freezing level. For an actual outing — say, a dawn ski-touring approach to the Maladeta — the "go / no-go" call depends on cross-checking eight or ten of those variables at once against a specific judgement: manageable mean wind on the ridge, freezing level high enough that the snowpack is not rotten, no probable afternoon storm, low cloud cover for navigation on the glacier, gusts tolerable on the arête. That cross-check lives in the experienced mountaineer's head; not on any screen. The tool formalises it: the thresholds are mine, the rules sit in a readable YAML file, and the traffic light always comes with the reasons that fired it. The output that the user sees does not hide the criteria that produced it; every colour is auditable and can be recalibrated. The approach — encoding expert judgement as auditable rules over model data — transfers to other settings of operational decision making on data: agriculture, rural energy, territorial management.

---

## Pieza 4 — Post LinkedIn (8-12 líneas)

Uso: soft launch. No anuncio de producto, no llamada a la acción
agresiva. "Construí esto y aquí está".

### Español

[Pendiente de publicar tras revisión final]

Decidir si una salida concreta de montaña es viable o no exige cruzar varias variables meteorológicas a la vez: temperatura, viento medio, ráfagas, cero térmico, nubosidad, precipitación, índice convectivo. Las apps meteorológicas las muestran como datos crudos. El cruce, con criterio de la actividad concreta —no es lo mismo skimo que alpinismo invernal o que trail— vive en la cabeza del montañero con experiencia.

Llevo unas semanas con un proyecto personal que intenta formalizar ese cruce: meteo-pirineo. Consume la previsión horaria de un modelo numérico profesional (Météo-France ARPEGE) vía Open-Meteo y devuelve un semáforo por actividad y día, con los motivos del color a la vista y la mejor y peor ventana dentro de la franja útil. Cinco actividades, dos zonas del Pirineo central. Pipeline diario en producción, sitio público que se regenera cada mañana con GitHub Actions.

Es una versión inicial. Hay cosas que sé que faltan y todavía no he hecho: combinar varios modelos para tener mejor robustez (ahora solo uso ARPEGE, los modelos privados están detrás de pago), ajustar las activaciones por estación (alpinismo invernal no debería evaluarse igual en julio que en febrero), refinar los umbrales contra observación real, ampliar a más zonas. Todo eso está identificado como deuda en el repositorio.

Lo que sí está hecho: la lógica de evaluación es declarativa (umbrales en YAML, no en código), las decisiones de arquitectura están documentadas en ADRs, hay tests automatizados de la lógica, y la herramienta lleva varias semanas funcionando para mis propias salidas.

Comparto el enlace por si a alguien le resulta útil o quiere comentar el enfoque. El código es abierto.

Sitio: https://falce-source.github.io/meteo-pirineo/
Código: https://github.com/Falce-source/meteo-pirineo

### English

[Pendiente de publicar tras revisión final]

Deciding whether a specific mountain outing is viable or not requires cross-checking several weather variables at once: temperature, mean wind, gusts, freezing level, cloud cover, precipitation, convective index. Weather apps show them as raw data. The cross-check, with judgement specific to the activity — ski touring is not the same as winter alpinism or trail running — lives in the head of the experienced mountaineer.

I have been working on a personal project for a few weeks that tries to formalise that cross-check: meteo-pirineo. It consumes hourly forecasts from a professional numerical weather model (Météo-France ARPEGE) via Open-Meteo and returns a traffic-light verdict per activity per day, with the reasons for each colour in plain view, plus the best and worst window within the active timeframe. Five activities, two zones in the central Pyrenees. Daily pipeline in production, public site that regenerates each morning through GitHub Actions.

It is an early version. There are things I know are missing and I have not done yet: combining several models for better robustness (I am only using ARPEGE for now, private models are behind paywalls), adjusting activity triggers by season (winter alpinism should not be evaluated the same in July as in February), refining thresholds against real observation, expanding to more zones. All of that is tracked as debt in the repository.

What is done: the evaluation logic is declarative (thresholds in YAML, not in code), architecture decisions are documented in ADRs, the logic has automated tests, and the tool has been running for several weeks for my own outings.

I share the link in case anyone finds it useful or wants to discuss the approach. The code is open.

Site: https://falce-source.github.io/meteo-pirineo/
Code: https://github.com/Falce-source/meteo-pirineo

---

## Pieza 5 — Mensaje conversacional (3-4 líneas)

Uso: respuestas a "cuéntame qué estás haciendo en datos",
introducciones por WhatsApp/email a contactos profesionales.
Sin enlaces obligatorios, dejarlos al final como referencia
opcional.

### Español

Últimamente he estado construyendo una herramienta para mí: codifica el criterio que uso para decidir si una actividad de montaña pinta bien o no según el pronóstico. Salió pequeña, pero me ha servido para pensar en cómo se traduce conocimiento de dominio en decisión operativa basada en datos. La estoy usando en cada salida y refinando con la experiencia. Por si quieres echarle un vistazo: falce-source.github.io/meteo-pirineo

### English

I have been building a small tool for myself: it encodes the judgement I use to decide whether a mountain outing looks workable based on the forecast. It is modest, but it has been a useful way to think about translating domain knowledge into data-driven operational decisions. I am using it on every outing and refining as experience accumulates. In case you want a look: falce-source.github.io/meteo-pirineo

---

## Notas de uso

- Si el interlocutor es técnico (ingeniero, científico de datos, CTO),
  usar piezas 2 y 4.
- Si el interlocutor es producto/negocio (PM, gerente, fundador), usar
  piezas 1 y 3.
- Si el interlocutor es no profesional o lazo personal, usar pieza 5.
- Pieza 4 (post LinkedIn) NO publicar antes de tener 4-5 entradas
  en `docs/uso_real.md`. Razón: el post se beneficia de poder citar
  uso real sostenido, no solo de la existencia del repo.
- Las URLs canónicas cambian solo si se renombra el repositorio o se
  cambia el username de GitHub. Si eso ocurre, actualizar este archivo
  completo.
