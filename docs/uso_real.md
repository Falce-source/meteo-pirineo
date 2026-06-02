# Registro de uso real

Datos crudos para calibrar umbrales y decidir si la opción C de
rediseño por franjas (ADR-008) tiene sentido.

Formato libre. Lo importante es que esté.

---

## Plantilla por salida

- **Fecha**:
- **Zona**:
- **Actividad**:
- **Cuándo consulté la herramienta**: (mañana, noche anterior, etc.)
- **Semáforo que mostró**: (si lo recuerdo / no consultado)
- **Mejor ventana sugerida**: (si lo recuerdo / no consultado)
- **Decisión que tomé**: (salí / no salí / cambié plan / etc.)
- **Qué me encontré realmente**:
- **¿La herramienta acertó?**: (sí / parcialmente / no / no aplicable)
- **Notas**:

---

## Salidas

### 2026-05-24 — Garmo Negro desde Balneario de Panticosa

- **Zona**: Pirineo aragonés (Panticosa-Garmo Negro, ~3050 m).
  Nota: zona no cubierta directamente por las dos zonas de v0.1
  (Benasque-Cerler y Aran-Baqueira). La consulta meteo se hizo en
  apps externas, no en la herramienta.
- **Actividad**: alpinismo estival / ascensión cumbre 3000.
- **Cuándo consulté la herramienta**: no consultada para esta salida
  (zona fuera de cobertura v0.1).
- **Pronóstico externo recordado**: tormentas por la tarde.
- **Decisión que tomé**: salí.
- **Qué me encontré realmente**: buen día, calor, sin tormenta vespertina.
- **¿La herramienta acertó?**: no aplicable (no consultada). El pronóstico
  externo dio falso positivo de tormenta.
- **Notas**: dato útil para validar el módulo tormenta de la herramienta
  cuando se incorpore esta zona o se haga consulta cruzada manual: si
  el módulo hubiera dado tormenta en este día, habría sido falso positivo.
  Pendiente comprobar retroactivamente si el output del cron del 24-may
  marcaba tormenta para Benasque (zona próxima).

### 2026-05-29 — [añadir actividad y zona si la recuerdas]

- **Zona**: Pirineo aragonés (zona próxima a Benasque, día previo a
  la salida del 30-may).
- **Actividad**: descanso (previo a carrera)
- **Cuándo consulté la herramienta**: no consultada (recordado de pronóstico
  externo).
- **Pronóstico externo recordado**: tormentas por la tarde.
- **Decisión que tomé**: [no salí porque tenía descanso, sino habría salido]
- **Qué me encontré realmente**: llovió, menos intenso que el día siguiente.
- **¿La herramienta acertó?**: no aplicable (no consultada). El pronóstico
  externo acertó parcialmente.

### 2026-05-30 — Carrera Castejón de Sos / Rincón del Cielo (Cerler)

- **Zona**: Benasque/Cerler (sí cubierta por la herramienta).
- **Actividad**: trail running.
- **Cuándo consulté la herramienta**: no consultada (registro retroactivo).
- **Pronóstico externo recordado**: tormentas por la tarde.
- **Decisión que tomé**: salí (carrera planificada).
- **Qué me encontré realmente**: llovió bastante por la tarde.
- **¿La herramienta acertó?**: no aplicable (no consultada). El pronóstico
  externo acertó.
- **Notas**: zona cubierta por v0.1, pero no se usó la herramienta.
  Pendiente revisar retroactivamente qué semáforo dio la herramienta
  para trail Benasque 30-may si está en histórico de commits.

---

## Observaciones agregadas (a actualizar a medida que crezca el registro)

**Patrón inicial (n=3)**: pronósticos de tormenta vespertina en los
3 días registrados. 1 falso positivo (24-may), 2 aciertos o aciertos
parciales (29-may, 30-may). Muestra demasiado pequeña para acción.
Vigilar si el módulo tormenta tiende a falso positivo en días de calor
sin convección real.

**Salidas no consultadas en herramienta**: las 3 salidas registradas
fueron consultadas en apps externas. Pendiente cambio de hábito:
consultar la herramienta antes de cada salida y registrar el output.