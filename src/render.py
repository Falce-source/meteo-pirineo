"""Render HTML estático a partir de la estructura de evaluaciones.

Genera ``docs/index.html`` autocontenido (CSS + JS inline, sin
peticiones externas). Pensado para servirse desde GitHub Pages.

API pública:
    renderizar_html(evaluaciones_por_zona, timestamp, modelo,
                    actividades, output_path)

Decisiones de diseño:
- Cero dependencias en runtime (solo stdlib).
- HTML5 + ``<dialog>`` nativo.
- Glifo + color para accesibilidad (daltonismo).
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.evaluar import EvaluacionDia

# Glifos accesibles: forma + color. Coinciden con la paleta CSS.
GLIFOS_HTML: dict[str, str] = {
    "VERDE": "✓",
    "AMBAR": "!",
    "ROJO": "✗",
    "SIN_DATOS": "–",
}

CLASE_CSS: dict[str, str] = {
    "VERDE": "verde",
    "AMBAR": "ambar",
    "ROJO": "rojo",
    "SIN_DATOS": "sin-datos",
}

MESES_ES_CORTO: dict[int, str] = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

# CSS embebido. Sin Google Fonts, sin recursos externos.
CSS_INLINE = """\
*,*::before,*::after { box-sizing: border-box; }
html,body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #1f2937;
  background: #ffffff;
  line-height: 1.45;
  font-size: 16px;
}
.contenedor { max-width: 1100px; margin: 0 auto; padding: 1rem; }
header.principal { padding: 1.25rem 0 0.5rem; border-bottom: 1px solid #e5e7eb; }
header.principal h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
.meta-actualizacion { color: #6b7280; font-size: 0.9rem; }
.aviso-aludes {
  background: #fff7ed;
  border-left: 4px solid #d97706;
  padding: 0.75rem 1rem;
  margin: 1rem 0;
  border-radius: 4px;
  font-size: 0.95rem;
}
.aviso-aludes strong { display: block; margin-bottom: 0.25rem; }
.aviso-aludes ul { margin: 0.25rem 0 0; padding-left: 1.25rem; }
.aviso-aludes a { color: #b45309; }
.zona { margin: 1.5rem 0; }
.zona h2 { font-size: 1.2rem; margin: 0 0 0.25rem; }
.zona .meta {
  margin: 0 0 0.5rem; color: #6b7280; font-size: 0.85rem;
}
.zona .meta a { color: #6b7280; text-decoration: underline; }
table.semaforos {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
table.semaforos thead th {
  font-weight: 600;
  color: #4b5563;
  border-bottom: 1px solid #e5e7eb;
  font-size: 0.8rem;
  padding: 0.4rem 0.2rem;
}
table.semaforos thead th:first-child { text-align: left; }
table.semaforos tbody th {
  text-align: left;
  font-weight: 500;
  color: #1f2937;
  padding: 0.4rem 0.4rem 0.4rem 0;
  font-size: 0.85rem;
  vertical-align: middle;
  word-break: break-word;
  hyphens: auto;
}
table.semaforos td { padding: 0.2rem; text-align: center; }
table.semaforos th:first-child { width: 38%; }
table.semaforos th:not(:first-child) { width: 12.4%; }

button.celda {
  font: inherit;
  width: 100%;
  min-width: 44px;
  min-height: 44px;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 1.35rem;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.05s ease;
}
button.celda:active { transform: scale(0.96); }
button.celda:focus-visible {
  outline: 3px solid #2563eb;
  outline-offset: 2px;
}
button.celda.verde     { background: #dcfce7; color: #16a34a; border-color: #86efac; }
button.celda.ambar     { background: #fef3c7; color: #d97706; border-color: #fcd34d; }
button.celda.rojo      { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }
button.celda.sin-datos { background: #f5f5f5; color: #737373; border-color: #d4d4d4; }

footer.principal {
  padding: 1rem 0;
  margin-top: 2rem;
  border-top: 1px solid #e5e7eb;
  color: #6b7280;
  font-size: 0.85rem;
}
footer.principal a { color: #6b7280; }

dialog#detalle {
  border: 1px solid #d1d5db;
  border-radius: 10px;
  padding: 1.1rem 1.2rem 1.2rem;
  max-width: 92vw;
  width: 480px;
  max-height: 85vh;
  color: #1f2937;
  box-shadow: 0 10px 30px rgba(0,0,0,0.12);
}
dialog#detalle::backdrop { background: rgba(15, 23, 42, 0.45); }
#detalle-titulo {
  margin: 0 0 0.25rem;
  font-size: 1.1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
#detalle-meta { color: #6b7280; font-size: 0.85rem; margin: 0 0 0.75rem; }
#detalle-cuerpo h4 { margin: 0.75rem 0 0.3rem; font-size: 0.9rem; color: #4b5563; }
#detalle-cuerpo ul { margin: 0; padding-left: 1.1rem; }
#detalle-cuerpo li { padding: 0.15rem 0; font-size: 0.9rem; }
#detalle-cuerpo dl.datos-clave {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.15rem 0.6rem;
  margin: 0;
  font-size: 0.85rem;
}
#detalle-cuerpo dl.datos-clave dt { color: #6b7280; }
#detalle-cuerpo dl.datos-clave dd { margin: 0; font-variant-numeric: tabular-nums; }
.nivel-ROJO  { color: #dc2626; font-weight: 600; }
.nivel-AMBAR { color: #d97706; font-weight: 600; }
.nivel-INFORMATIVO { color: #2563eb; font-weight: 500; }
button#detalle-cerrar {
  margin-top: 1rem;
  background: #1f2937;
  color: #f9fafb;
  border: 0;
  padding: 0.55rem 0.9rem;
  border-radius: 6px;
  cursor: pointer;
  font: inherit;
}
button#detalle-cerrar:hover { background: #111827; }

@media (max-width: 480px) {
  .contenedor { padding: 0.75rem; }
  header.principal h1 { font-size: 1.25rem; }
  table.semaforos thead th { font-size: 0.7rem; }
  table.semaforos tbody th { font-size: 0.78rem; }
  button.celda { font-size: 1.15rem; }
}
"""

JS_INLINE = """\
(function () {
  const dialog = document.getElementById('detalle');
  const titulo = document.getElementById('detalle-titulo');
  const meta = document.getElementById('detalle-meta');
  const cuerpo = document.getElementById('detalle-cuerpo');
  const cerrar = document.getElementById('detalle-cerrar');

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  }

  function fmtValor(v, unidad) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      const n = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1);
      return unidad ? n + ' ' + unidad : n;
    }
    return String(v);
  }

  function fmtUmbral(m) {
    if (m.umbral_disparado === null || m.umbral_disparado === undefined) return '';
    const opStr = (m.op && m.op !== 'informativo') ? m.op : '';
    const v = Math.abs(m.umbral_disparado) >= 100
      ? m.umbral_disparado.toFixed(0)
      : m.umbral_disparado.toFixed(0);
    const unidad = m.unidad ? ' ' + m.unidad : '';
    return opStr + v + unidad;
  }

  document.addEventListener('click', function (e) {
    const btn = e.target.closest('button.celda');
    if (!btn) return;
    const zona = btn.dataset.zonaNombre || '';
    const actividad = btn.dataset.actividadNombre || '';
    const fecha = btn.dataset.fechaLarga || btn.dataset.fecha || '';
    const semaforo = btn.dataset.semaforo || '';
    const motivos = JSON.parse(btn.dataset.motivos || '[]');
    const avisos = JSON.parse(btn.dataset.avisos || '[]');
    const datosClave = JSON.parse(btn.dataset.datosClave || '{}');

    const glifo = btn.textContent.trim();
    titulo.innerHTML = '<span class="celda-mini ' + escapeHTML(btn.classList.contains('verde') ? 'verde' : btn.classList.contains('ambar') ? 'ambar' : btn.classList.contains('rojo') ? 'rojo' : 'sin-datos') + '">' + escapeHTML(glifo) + '</span>'
      + escapeHTML(actividad);
    meta.textContent = zona + ' — ' + fecha + ' — ' + semaforo;

    let html = '';
    if (motivos.length) {
      html += '<h4>Motivos</h4><ul>';
      motivos.forEach(function (m) {
        const valor = fmtValor(m.valor_observado, m.unidad);
        const umbral = fmtUmbral(m);
        const umbralTxt = umbral ? ' (umbral ' + escapeHTML((m.nivel || '').toLowerCase()) + ': ' + escapeHTML(umbral) + ')' : '';
        const estimada = m.estimada ? ' <em>[estimado]</em>' : '';
        html += '<li><span class="nivel-' + escapeHTML(m.nivel || '') + '">[' + escapeHTML(m.nivel || '') + ']</span> '
          + escapeHTML(m.descripcion || m.variable || '') + ': ' + escapeHTML(valor) + umbralTxt + estimada + '</li>';
      });
      html += '</ul>';
    }
    if (avisos.length) {
      html += '<h4>Avisos</h4><ul>';
      avisos.forEach(function (a) { html += '<li>' + escapeHTML(a) + '</li>'; });
      html += '</ul>';
    }
    if (Object.keys(datosClave).length) {
      html += '<h4>Datos clave</h4><dl class="datos-clave">';
      Object.keys(datosClave).forEach(function (k) {
        const v = datosClave[k];
        const vs = (typeof v === 'number') ? (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)) : v;
        html += '<dt>' + escapeHTML(k) + '</dt><dd>' + escapeHTML(vs) + '</dd>';
      });
      html += '</dl>';
    }
    if (!html) html = '<p>Sin motivos ni avisos disparados para este día.</p>';
    cuerpo.innerHTML = html;

    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  });

  cerrar.addEventListener('click', function () { dialog.close(); });
  dialog.addEventListener('click', function (e) {
    const rect = dialog.getBoundingClientRect();
    const fuera = e.clientX < rect.left || e.clientX > rect.right
      || e.clientY < rect.top || e.clientY > rect.bottom;
    if (fuera) dialog.close();
  });
})();
"""


# ----------------------------------------------------------------------
# Helpers de formato
# ----------------------------------------------------------------------

def _fmt_fecha_corta(d) -> str:
    return f"{d.day:02d}-{MESES_ES_CORTO[d.month]}"


def _fmt_fecha_larga(d) -> str:
    return f"{d.day:02d}-{MESES_ES_CORTO[d.month]}-{d.year}"


def _attr(value: Any) -> str:
    """Serializa cualquier estructura JSON-segura para un atributo HTML."""
    j = json.dumps(value, ensure_ascii=False, default=str)
    return html.escape(j, quote=True)


def _e(text: Any) -> str:
    """HTML-escape de texto plano."""
    return html.escape(str(text), quote=True)


# ----------------------------------------------------------------------
# Constructores de fragmentos
# ----------------------------------------------------------------------

def _render_header(timestamp: datetime, modelo: str) -> str:
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M")
    return f"""\
<header class="principal">
  <h1>Meteo Pirineo — actividades de montaña</h1>
  <p class="meta-actualizacion">
    Actualizado: <time datetime="{_e(timestamp.isoformat())}">{_e(ts_str)}</time>
    — modelo: <code>{_e(modelo)}</code>
  </p>
</header>
"""


def _render_aviso_aludes(evaluaciones_por_zona: dict[str, Any]) -> str:
    """Bloque de aviso con enlaces a boletines oficiales."""
    boletines: list[dict[str, str]] = []
    seen: set[str] = set()
    for paquete in evaluaciones_por_zona.values():
        zona = paquete["zona"]
        bol = zona.get("boletin_aludes") or {}
        url = bol.get("url")
        if url and url not in seen:
            seen.add(url)
            boletines.append({
                "macizo": zona.get("macizo", ""),
                "nombre": bol.get("nombre", url),
                "url": url,
            })
    if not boletines:
        return ""
    items = "".join(
        f'    <li><strong>{_e(b["macizo"])}:</strong> '
        f'<a href="{_e(b["url"])}" target="_blank" rel="noopener">'
        f'{_e(b["nombre"])}</a></li>\n'
        for b in boletines
    )
    return f"""\
<aside class="aviso-aludes">
  <strong>Esta herramienta NO predice aludes.</strong>
  Para condiciones nivológicas consulta siempre el boletín oficial:
  <ul>
{items}  </ul>
</aside>
"""


def _render_celda(
    zona: dict[str, Any],
    actividad: dict[str, Any],
    fecha,
    evaluacion: EvaluacionDia | None,
) -> str:
    if evaluacion is None:
        clase = CLASE_CSS["SIN_DATOS"]
        glifo = GLIFOS_HTML["SIN_DATOS"]
        return (
            f'<td><button type="button" class="celda {clase}" '
            f'aria-label="Sin evaluación" disabled>{glifo}</button></td>'
        )

    clase = CLASE_CSS.get(evaluacion.semaforo, "sin-datos")
    glifo = GLIFOS_HTML.get(evaluacion.semaforo, "?")
    motivos_data = [asdict(m) for m in evaluacion.motivos]
    avisos_data = list(evaluacion.avisos)
    datos_clave_data = {k: round(float(v), 3) for k, v in evaluacion.datos_clave.items()}

    cell_id = f"{zona['id']}-{actividad['id']}-{fecha.isoformat()}"
    aria = (
        f"{actividad['nombre']} en {zona['nombre']} el {_fmt_fecha_larga(fecha)}: "
        f"{evaluacion.semaforo.lower()}"
    )

    return (
        f'<td>'
        f'<button type="button" id="{_e(cell_id)}" class="celda {clase}" '
        f'aria-label="{_e(aria)}" '
        f'data-zona="{_e(zona["id"])}" '
        f'data-zona-nombre="{_e(zona["nombre"])}" '
        f'data-actividad="{_e(actividad["id"])}" '
        f'data-actividad-nombre="{_e(actividad["nombre"])}" '
        f'data-fecha="{_e(fecha.isoformat())}" '
        f'data-fecha-larga="{_e(_fmt_fecha_larga(fecha))}" '
        f'data-semaforo="{_e(evaluacion.semaforo)}" '
        f'data-motivos="{_attr(motivos_data)}" '
        f'data-avisos="{_attr(avisos_data)}" '
        f'data-datos-clave="{_attr(datos_clave_data)}"'
        f'>{glifo}</button>'
        f'</td>'
    )


def _render_zona(
    zona: dict[str, Any],
    actividades: list[dict[str, Any]],
    evaluaciones: list[EvaluacionDia],
    fechas: list,
) -> str:
    por_clave: dict[tuple[str, Any], EvaluacionDia] = {
        (ev.actividad_id, ev.fecha): ev for ev in evaluaciones
    }
    bol = zona.get("boletin_aludes") or {}
    meta_aludes = ""
    if bol.get("url"):
        meta_aludes = (
            f' · Boletín de aludes: '
            f'<a href="{_e(bol["url"])}" target="_blank" rel="noopener">'
            f'{_e(bol.get("nombre", "enlace"))}</a>'
        )

    thead_cols = "".join(
        f'<th scope="col">{_e(_fmt_fecha_corta(f))}</th>' for f in fechas
    )

    filas = []
    for act in actividades:
        celdas = "".join(
            _render_celda(zona, act, f, por_clave.get((act["id"], f)))
            for f in fechas
        )
        filas.append(
            f'<tr><th scope="row">{_e(act["nombre"])}</th>{celdas}</tr>'
        )

    return f"""\
<section class="zona" id="{_e("zona-" + zona["id"])}">
  <h2>{_e(zona["nombre"])}</h2>
  <p class="meta">
    {_e(zona["latitud"])}°N, {_e(zona["longitud"])}°E · {_e(zona["elevacion_m"])} m
    · {_e(zona.get("macizo", ""))}{meta_aludes}
  </p>
  <table class="semaforos">
    <thead>
      <tr><th scope="col">Actividad</th>{thead_cols}</tr>
    </thead>
    <tbody>
      {"".join(filas)}
    </tbody>
  </table>
</section>
"""


def _render_footer() -> str:
    return """\
<footer class="principal">
  <p>
    Herramienta personal, no garantizada. Consulta siempre boletines
    oficiales para condiciones nivológicas y meteorología de montaña.
  </p>
  <p>
    Código: <a href="https://github.com/" target="_blank" rel="noopener">repositorio en GitHub</a>
    · v0.1
  </p>
</footer>
"""


def _render_dialog() -> str:
    return """\
<dialog id="detalle">
  <h3 id="detalle-titulo"></h3>
  <p id="detalle-meta"></p>
  <div id="detalle-cuerpo"></div>
  <button type="button" id="detalle-cerrar">Cerrar</button>
</dialog>
"""


# ----------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------

def renderizar_html(
    evaluaciones_por_zona: dict[str, dict[str, Any]],
    timestamp: datetime,
    modelo: str,
    actividades: list[dict[str, Any]],
    output_path: Path = Path("docs/index.html"),
) -> Path:
    """Genera el HTML estático y lo escribe en disco.

    Args:
        evaluaciones_por_zona: dict ``{zona_id: {"zona": dict,
            "evaluaciones": list[EvaluacionDia]}}``.
        timestamp: marca temporal de la actualización (datetime).
        modelo: identificador del modelo Open-Meteo usado.
        actividades: lista de actividades (orden de filas en la tabla).
        output_path: ruta destino. Se crean los directorios padre si no
            existen.

    Returns:
        Path absoluto del archivo escrito.
    """
    # Conjunto unificado de fechas (todas las zonas usan el mismo
    # horizonte, pero por seguridad unimos).
    fechas: list = sorted({
        ev.fecha
        for paquete in evaluaciones_por_zona.values()
        for ev in paquete["evaluaciones"]
    })

    secciones_zonas = []
    for zona_id in evaluaciones_por_zona:
        paquete = evaluaciones_por_zona[zona_id]
        secciones_zonas.append(
            _render_zona(
                zona=paquete["zona"],
                actividades=actividades,
                evaluaciones=paquete["evaluaciones"],
                fechas=fechas,
            )
        )

    cuerpo = (
        _render_header(timestamp, modelo)
        + _render_aviso_aludes(evaluaciones_por_zona)
        + "<main>\n"
        + "".join(secciones_zonas)
        + "</main>\n"
        + _render_footer()
        + _render_dialog()
    )

    html_doc = f"""\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meteo Pirineo</title>
<style>
{CSS_INLINE}</style>
</head>
<body>
<div class="contenedor">
{cuerpo}</div>
<script>
{JS_INLINE}</script>
</body>
</html>
"""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path.resolve()
