"""Orquestador end-to-end de meteo-pirineo.

Carga zonas y actividades, hace fetch contra Open-Meteo y renderiza
una tabla de semáforos por consola.

Ejecutar desde la raíz del repo:
    python -m src.main
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.derivadas import enriquecer_con_derivadas  # noqa: E402
from src.evaluar import (  # noqa: E402
    EvaluacionDia,
    cargar_actividades,
    evaluar_dia,
)
from src.fetch import (  # noqa: E402
    MODELO_DEFAULT,
    PrevisionMeteo,
    cargar_zonas,
    fetch_zona,
)
from src.render import renderizar_html  # noqa: E402

GLIFOS_SEMAFORO: dict[str, str] = {
    "VERDE": "🟢",
    "AMBAR": "🟡",
    "ROJO": "🔴",
    "SIN_DATOS": "⚪",
}

MESES_ES_CORTO: dict[int, str] = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

ANCHO_COL_FECHA = 8  # caracteres ASCII por columna de fecha
ANCHO_COL_ACT = 32   # ancho de la columna "Actividad"

logger = logging.getLogger("src.main")


def fmt_fecha_corta(d) -> str:
    return f"{d.day:02d}-{MESES_ES_CORTO[d.month]}"


def fechas_disponibles(evaluaciones: list[EvaluacionDia]) -> list:
    return sorted({ev.fecha for ev in evaluaciones})


def elegir_peor_dia(evaluaciones: list[EvaluacionDia]) -> object | None:
    """Devuelve la fecha más complicada de una zona.

    Criterio: más rojos → más ámbares → orden temporal.
    """
    if not evaluaciones:
        return None
    por_fecha: dict = {}
    for ev in evaluaciones:
        c = por_fecha.setdefault(ev.fecha, Counter())
        c[ev.semaforo] += 1
    fechas_ordenadas = sorted(por_fecha.keys())
    return max(
        fechas_ordenadas,
        key=lambda f: (
            por_fecha[f].get("ROJO", 0),
            por_fecha[f].get("AMBAR", 0),
            -fechas_ordenadas.index(f),  # antes empata = preferido
        ),
    )


def _fmt_valor(v: float | None, unidad: str | None) -> str:
    if v is None:
        return "—"
    if unidad in {"%", "°C", "km/h", "mm/h", "cm", "m"}:
        if abs(v) >= 100:
            return f"{v:.0f} {unidad}"
        return f"{v:.1f} {unidad}"
    if unidad:
        return f"{v:.1f} {unidad}"
    return f"{v:.1f}"


def _fmt_umbral(
    v: float | None,
    nivel: str,
    unidad: str | None,
    op: str | None,
) -> str:
    if v is None:
        return f"umbral {nivel.lower()}: n/a"
    # Mantener el operador comparativo en la cadena para que el usuario
    # vea explícitamente el sentido del umbral (>, <, etc.).
    prefijo_op = op if op and op != "informativo" else ""
    if unidad:
        return f"umbral {nivel.lower()}: {prefijo_op}{v:.0f} {unidad}"
    return f"umbral {nivel.lower()}: {prefijo_op}{v:.0f}"


def imprimir_tabla_zona(
    zona: dict,
    actividades: list[dict],
    evaluaciones: list[EvaluacionDia],
    fecha_fetch: datetime,
    modelo: str,
) -> None:
    fechas = fechas_disponibles(evaluaciones)
    titulo = (
        f"ZONA: {zona['nombre']} — "
        f"{zona['latitud']}°N, {zona['longitud']}°E, "
        f"{zona['elevacion_m']} m"
    )
    raya = "=" * 80
    print()
    print(raya)
    print(titulo)
    print(
        f"Última actualización: {fecha_fetch:%Y-%m-%d %H:%M} "
        f"(modelo: {modelo})"
    )
    print(raya)
    print()

    # Cabecera tabla.
    header = f"{'Actividad':<{ANCHO_COL_ACT}}"
    for f in fechas:
        header += fmt_fecha_corta(f).ljust(ANCHO_COL_FECHA)
    print(header)
    print("-" * (ANCHO_COL_ACT + ANCHO_COL_FECHA * len(fechas)))

    # Index por (actividad_id, fecha) para acceso rápido.
    por_clave: dict[tuple[str, object], EvaluacionDia] = {
        (ev.actividad_id, ev.fecha): ev for ev in evaluaciones
    }

    for act in actividades:
        fila = f"{act['nombre'][:ANCHO_COL_ACT]:<{ANCHO_COL_ACT}}"
        for f in fechas:
            ev = por_clave.get((act["id"], f))
            if ev is None:
                fila += " " * ANCHO_COL_FECHA
            else:
                # Glifo + padding. Emoji ocupa ~2 celdas visuales, pero
                # 1 carácter en string. Compensamos con ANCHO_COL_FECHA-2
                # espacios para que la siguiente columna quede alineada
                # en terminales que renderizan el emoji ancho.
                glifo = GLIFOS_SEMAFORO.get(ev.semaforo, "?")
                fila += glifo + " " * (ANCHO_COL_FECHA - 2)
        print(fila)

    # Avisos de zona (deduplicados).
    avisos_zona = {
        a for ev in evaluaciones for a in ev.avisos
        if "boletín de aludes" in a.lower()
    }
    if avisos_zona:
        print()
        print("Avisos zona:")
        for a in sorted(avisos_zona):
            print(f"  - {a}")

    # Día más complicado. Solo se imprime si la zona tiene al menos
    # un AMBAR o ROJO en algún día y actividad (Semana 2.5).
    hay_alerta_en_zona = any(
        ev.semaforo in ("AMBAR", "ROJO") for ev in evaluaciones
    )
    if not hay_alerta_en_zona:
        return

    peor = elegir_peor_dia(evaluaciones)
    if peor is None:
        return
    evs_peor = [ev for ev in evaluaciones if ev.fecha == peor]
    interesantes = [
        ev for ev in evs_peor
        if any(m.nivel in ("ROJO", "AMBAR") for m in ev.motivos)
        or any("pendiente" in a.lower() for a in ev.avisos)
    ]
    if not interesantes:
        return

    nombre_por_id = {a["id"]: a["nombre"] for a in actividades}
    print()
    print(f"Motivos del día más complicado ({fmt_fecha_corta(peor)}):")
    for ev in interesantes:
        nombre = nombre_por_id.get(ev.actividad_id, ev.actividad_id)
        print(f"  - {nombre} ({ev.semaforo}):")
        for m in ev.motivos:
            if m.nivel not in ("ROJO", "AMBAR"):
                continue
            valor_s = _fmt_valor(m.valor_observado, m.unidad)
            umbral_s = _fmt_umbral(
                m.umbral_disparado, m.nivel, m.unidad, m.op
            )
            estimada_s = " [estimado]" if m.estimada else ""
            print(
                f"      · {m.descripcion}: {valor_s} ({umbral_s})"
                f"{estimada_s}"
            )
        # Mostrar también los informativos si los hay.
        for m in ev.motivos:
            if m.nivel != "INFORMATIVO":
                continue
            valor_s = _fmt_valor(m.valor_observado, m.unidad)
            estimada_s = " [estimado]" if m.estimada else ""
            print(f"      · [INFO] {m.descripcion}: {valor_s}{estimada_s}")
        # Avisos pendientes (variable derivada o no disponible).
        for a in ev.avisos:
            if "pendiente" in a.lower():
                print(f"      ⚠ {a}")


def evaluar_zona(
    prevision: PrevisionMeteo,
    actividades: list[dict],
) -> list[EvaluacionDia]:
    fechas: list = sorted({ts.date() for ts in prevision.horario.index})
    salida: list[EvaluacionDia] = []
    for fecha in fechas:
        for act in actividades:
            salida.append(evaluar_dia(prevision, act, fecha))
    return salida


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="meteo-pirineo",
        description=(
            "Orquestador: fetch + evaluación + render. Por defecto "
            "imprime tabla por consola Y genera HTML estático."
        ),
    )
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument(
        "--solo-consola",
        action="store_true",
        help="No generar HTML, solo imprimir tabla por consola.",
    )
    grupo.add_argument(
        "--solo-html",
        action="store_true",
        help="No imprimir tabla, solo generar HTML.",
    )
    p.add_argument(
        "--output",
        default="docs",
        help="Carpeta de salida para el HTML (default: docs/).",
    )
    return p.parse_args(argv)


def main(
    zonas: Iterable[dict] | None = None,
    modelo: str = MODELO_DEFAULT,
    modo: str = "ambos",
    output_dir: str | Path = "docs",
) -> None:
    """Orquesta el pipeline completo.

    Args:
        zonas: iterable de zonas; si ``None``, se cargan desde
            ``config/zonas.yaml``.
        modelo: identificador del modelo Open-Meteo.
        modo: ``"ambos"``, ``"consola"`` o ``"html"``.
        output_dir: carpeta donde se escribe ``index.html`` en los
            modos que generan HTML.
    """
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if zonas is None:
        zonas = cargar_zonas()
    actividades = cargar_actividades()

    consola_activa = modo in ("ambos", "consola")
    html_activo = modo in ("ambos", "html")

    paquetes_por_zona: dict[str, dict] = {}
    timestamp_global: datetime | None = None

    for zona in zonas:
        prevision = fetch_zona(zona, modelo=modelo)
        prevision.horario = enriquecer_con_derivadas(
            prevision.horario, zona["elevacion_m"]
        )
        evaluaciones = evaluar_zona(prevision, actividades)

        paquetes_por_zona[zona["id"]] = {
            "zona": zona,
            "evaluaciones": evaluaciones,
        }
        if timestamp_global is None or prevision.timestamp_fetch > timestamp_global:
            timestamp_global = prevision.timestamp_fetch

        if consola_activa:
            imprimir_tabla_zona(
                zona=zona,
                actividades=actividades,
                evaluaciones=evaluaciones,
                fecha_fetch=prevision.timestamp_fetch,
                modelo=modelo,
            )

    if consola_activa:
        print()

    if html_activo and paquetes_por_zona:
        ts = timestamp_global or datetime.now()
        output_path = Path(output_dir) / "index.html"
        path = renderizar_html(
            evaluaciones_por_zona=paquetes_por_zona,
            timestamp=ts,
            modelo=modelo,
            actividades=actividades,
            output_path=output_path,
        )
        print(f"HTML generado en: {path}")


if __name__ == "__main__":
    args = parse_args()
    if args.solo_consola:
        modo = "consola"
    elif args.solo_html:
        modo = "html"
    else:
        modo = "ambos"
    main(modo=modo, output_dir=args.output)
