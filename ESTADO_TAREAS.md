# ESTADO_TAREAS.md — Bitácora operativa de meteo-pirineo

> Foto del estado actual del repo y tareas pendientes. Actualizar al
> final de cada sesión. Para el contexto estable del proyecto, ver
> `CLAUDE.md`.

## Estado del repo (actualizado: 2026-06-16)

- **Ubicación canónica**: `C:\Users\afalceto\repos\meteo-pirineo` (FUERA
  de OneDrive). Migrado desde OneDrive el 2026-06-16.
- **Remoto**: https://github.com/Falce-source/meteo-pirineo (rama `main`).
- **Sitio público**: https://falce-source.github.io/meteo-pirineo/
- **Tests**: 61 pasando.
- **ADRs registrados**: 10 (ver `docs/decisiones.md`).
- **Cron diario**: activo, funcionando. Commitea `docs/index.html` a
  `main` cada mañana (~05-06 UTC, latencia variable).
- **Estado funcional**: completo y en producción. Features: evaluación por
  reglas declarativas, variables derivadas (cero térmico, índice tormenta),
  ventanas óptimas por actividad, activación por temporada.

## Flujo de trabajo recordatorio

- **Empezar sesión**: `git pull --rebase origin main`.
- **Terminar sesión**: commit + `git push`. Actualizar este archivo.
- **Conflicto en `docs/index.html`**: regenerar con
  `python -m src.main --solo-html`, no editar a mano.

## Tareas pendientes

### Migración fuera de OneDrive (en curso)

- [x] Verificar estado del repo y asegurar GitHub tiene todo (2026-06-16).
- [x] Clonar copia nueva fuera de OneDrive y verificar (2026-06-16).
- [x] Crear CLAUDE.md y ESTADO_TAREAS.md (2026-06-16).
- [ ] Borrar la copia de OneDrive (paso siguiente, con confirmación de ruta).
- [ ] **Clonar la copia nueva en el SEGUNDO ordenador (PC personal),
      también fuera de OneDrive**, en `C:\Users\afalceto\repos\`. Hacer
      físicamente desde esa máquina otro día:
      `cd C:\Users\afalceto\repos && gh repo clone Falce-source/meteo-pirineo`.
      Verificar con `git status` y `pytest`.

### Bloque 2 — uso real (en curso, sin código)

- [ ] Seguir registrando uso real en `docs/uso_real.md` antes de cada
      salida. Objetivo: acumular 4-6 salidas con la herramienta consultada
      para validar/recalibrar umbrales.
- [ ] Cuando haya datos suficientes: revisar si los umbrales de tormenta
      tienden a falso positivo (hipótesis abierta desde n=3).

### Deuda técnica menor (no urgente)

- [ ] Mover el deploy del cron a una rama `gh-pages` separada, para que el
      cron no commitee a `main` y se elimine la fricción recurrente de
      divergencia. Estimado ~30 min.
- [ ] Limpiar o borrar `scripts/validar_html.py`: su constante
      `CELDAS_ESPERADAS = 50` quedó obsoleta tras la activación por
      temporada (el número de celdas ya no es fijo).
- [ ] Añadir las capturas de pantalla a `docs/img/`. La carpeta no existe
      en el repo; `docs/material_comunicacion.md` referencia capturas que
      nunca se commitearon. Generar/añadir: captura_01_vista_general.png,
      captura_02_vista_movil_cabecera.png, captura_03_vista_movil_tabla.png,
      captura_04_modal_ventana.png.

### Roadmap futuro (no decidido, requiere uso real previo)

- [ ] Ampliar a más zonas (Ordesa, Cadí, Andorra, Panticosa...). Andrés
      usa zonas no cubiertas en salidas reales.
- [ ] Activación por estación más fina (rangos de fecha en vez de mes
      calendario) si el uso real revela que los bordes de transición
      generan ruido.
- [ ] Integración de un segundo modelo meteo para robustez (los modelos
      privados como Meteoblue/ECMWF de alta resolución están tras pago).
- [ ] Horizonte lejano: predicción a medio-largo plazo con modelos
      matemáticos/ML. Requiere base de datos histórica que aún no existe.

## Notas

- El parche `windows.appendAtomically false` que tenía la copia de OneDrive
  NO es necesario en la copia fuera de OneDrive (no se hereda al clonar).
- El post de LinkedIn (Pieza 4 en `docs/material_comunicacion.md`) está
  redactado pero APARCADO: Andrés es CTO en activo y prioriza discreción.
  Se usará en privado con contactos (Retree, Meteosim) cuando proceda.
