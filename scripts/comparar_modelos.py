"""Comparar viento entre modelos Open-Meteo para Benasque y Aran.

Script desechable de exploración. NO usar en producción.

Ejecutar desde la raíz del repo:
    python scripts/comparar_modelos.py
"""

from __future__ import annotations

import sys
from typing import Any

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = "temperature_2m,windspeed_10m,windgusts_10m"

ZONAS: list[dict[str, Any]] = [
    {
        "id": "benasque",
        "nombre": "BENASQUE",
        "latitud": 42.65,
        "longitud": 0.55,
        "elevacion_m": 2200,
    },
    {
        "id": "aran",
        "nombre": "ARAN",
        "latitud": 42.70,
        "longitud": 0.93,
        "elevacion_m": 2070,
    },
]

# Modelos a probar. Resolución nominal en km para análisis posterior.
MODELOS: list[tuple[str, float | None]] = [
    ("best_match", None),
    ("ecmwf_ifs025", 25.0),
    ("meteofrance_arpege_europe", 25.0),
    ("meteofrance_arome_france", 1.3),
    ("meteofrance_arome_france_hd", 0.5),
    ("icon_eu", 6.5),
]

FRANJA_INICIO = 7   # 07:00 hora local
FRANJA_FIN = 17     # 17:00 hora local (inclusive)


def call_modelo(zona: dict[str, Any], modelo: str) -> tuple[dict | None, str]:
    """Devuelve (payload, estado). estado='OK' o un mensaje de error corto."""
    params = {
        "latitude": zona["latitud"],
        "longitude": zona["longitud"],
        "elevation": zona["elevacion_m"],
        "forecast_days": 2,
        "timezone": "Europe/Madrid",
        "hourly": HOURLY_VARS,
        "models": modelo,
        "windspeed_unit": "kmh",
    }
    try:
        r = requests.get(URL, params=params, timeout=30)
    except requests.RequestException as e:
        return None, f"N/A ({type(e).__name__})"

    if r.status_code != 200:
        motivo = ""
        try:
            j = r.json()
            motivo = j.get("reason") or j.get("error") or ""
        except Exception:
            motivo = (r.text or "")[:60].replace("\n", " ")
        motivo = motivo.strip() or f"HTTP {r.status_code}"
        # Acortar si es muy largo.
        if len(motivo) > 60:
            motivo = motivo[:57] + "..."
        return None, f"N/A ({motivo})"

    return r.json(), "OK"


def metricas_franja(payload: dict, modelo: str) -> dict[str, Any]:
    """Calcula métricas en franja 07:00-17:00 (incl.) del día 1."""
    hourly = payload.get("hourly") or {}
    times: list[str] = hourly.get("time") or []
    if not times:
        return {
            "viento_medio": None,
            "rafaga_max": None,
            "elev_api": payload.get("elevation"),
        }

    primer_dia = times[0][:10]

    # Las claves de viento pueden venir como "windspeed_10m" o
    # "windspeed_10m_<modelo>" cuando se piden varios modelos. Aquí
    # pedimos uno solo, así que el nombre debería ser el plano, pero
    # toleramos ambos por seguridad.
    def col(name: str) -> list[Any]:
        if name in hourly:
            return hourly[name]
        return hourly.get(f"{name}_{modelo}", [])

    winds_all = col("windspeed_10m")
    gusts_all = col("windgusts_10m")

    winds: list[float] = []
    gusts: list[float] = []
    for i, t in enumerate(times):
        if not t.startswith(primer_dia):
            continue
        try:
            hora = int(t[11:13])
        except (ValueError, IndexError):
            continue
        if FRANJA_INICIO <= hora <= FRANJA_FIN:
            if i < len(winds_all) and winds_all[i] is not None:
                winds.append(float(winds_all[i]))
            if i < len(gusts_all) and gusts_all[i] is not None:
                gusts.append(float(gusts_all[i]))

    return {
        "viento_medio": (sum(winds) / len(winds)) if winds else None,
        "rafaga_max": max(gusts) if gusts else None,
        "elev_api": payload.get("elevation"),
    }


def fmt(v: Any, prec: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{prec}f}"
    return str(v)


def imprimir_tabla(zona: dict[str, Any], filas: list[dict[str, Any]]) -> None:
    titulo = (
        f"==== {zona['nombre']} ({zona['latitud']}, {zona['longitud']}, "
        f"elev pedida {zona['elevacion_m']}) ===="
    )
    print()
    print(titulo)
    print(
        f"{'modelo':<32} {'elev_API':<9} "
        f"{'viento_medio_d1':<16} {'rafaga_max_d1':<14} {'estado':<40}"
    )
    print("-" * 115)
    for f in filas:
        print(
            f"{f['modelo']:<32} "
            f"{fmt(f['elev_api'], 1):<9} "
            f"{fmt(f['viento_medio']):<16} "
            f"{fmt(f['rafaga_max']):<14} "
            f"{f['estado']:<40}"
        )


def main() -> None:
    resultados_por_zona: dict[str, list[dict[str, Any]]] = {}

    for zona in ZONAS:
        filas = []
        for modelo, _res_km in MODELOS:
            payload, estado = call_modelo(zona, modelo)
            if payload is None:
                filas.append(
                    {
                        "modelo": modelo,
                        "viento_medio": None,
                        "rafaga_max": None,
                        "elev_api": None,
                        "estado": estado,
                    }
                )
            else:
                m = metricas_franja(payload, modelo)
                filas.append(
                    {
                        "modelo": modelo,
                        "viento_medio": m["viento_medio"],
                        "rafaga_max": m["rafaga_max"],
                        "elev_api": m["elev_api"],
                        "estado": estado,
                    }
                )
        resultados_por_zona[zona["id"]] = filas
        imprimir_tabla(zona, filas)

    # ---- Análisis ----
    print()
    print("ANÁLISIS:")

    def rango(filas: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
        valores = [
            f["viento_medio"]
            for f in filas
            if f["estado"] == "OK" and f["viento_medio"] is not None
        ]
        if not valores:
            return None, None, None
        vmin, vmax = min(valores), max(valores)
        ratio = (vmax / vmin) if vmin > 0 else None
        return vmin, vmax, ratio

    for zona in ZONAS:
        filas = resultados_por_zona[zona["id"]]
        vmin, vmax, ratio = rango(filas)
        if vmin is None:
            print(
                f"- Rango de viento_medio_d1 en {zona['nombre']}: "
                f"sin datos OK"
            )
        else:
            ratio_s = "n/a (min=0)" if ratio is None else f"{ratio:.1f}"
            print(
                f"- Rango de viento_medio_d1 en {zona['nombre']}: "
                f"[{vmin:.2f}, {vmax:.2f}] km/h. Ratio max/min: {ratio_s}"
            )

    # Modelos OK en ambas zonas
    ok_benasque = {
        f["modelo"]
        for f in resultados_por_zona["benasque"]
        if f["estado"] == "OK"
    }
    ok_aran = {
        f["modelo"]
        for f in resultados_por_zona["aran"]
        if f["estado"] == "OK"
    }
    cobertura_ambas = ok_benasque & ok_aran
    # Ordenar según el orden original
    cobertura_ordenada = [m for m, _ in MODELOS if m in cobertura_ambas]
    print(
        f"- Modelos con cobertura para AMBAS zonas: "
        f"{cobertura_ordenada if cobertura_ordenada else 'ninguno'}"
    )

    # Mayor resolución disponible para ambas (menor km)
    resolucion = {nombre: res for nombre, res in MODELOS}
    candidatos = [
        (m, resolucion[m])
        for m in cobertura_ordenada
        if resolucion[m] is not None
    ]
    if candidatos:
        mejor = min(candidatos, key=lambda x: x[1])
        print(
            f"- Modelo con mayor resolución disponible para ambas: "
            f"{mejor[0]} (~{mejor[1]} km)"
        )
    else:
        print(
            "- Modelo con mayor resolución disponible para ambas: "
            "n/d (best_match es el único común o no hay candidatos con "
            "resolución conocida)"
        )


if __name__ == "__main__":
    main()
