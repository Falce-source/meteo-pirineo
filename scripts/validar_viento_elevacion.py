"""Validar qué representa windspeed_10m y qué efecto tiene `elevation`.

Script desechable de exploración. NO usar en producción.

Ejecutar desde la raíz del repo:
    python scripts/validar_viento_elevacion.py
"""

from __future__ import annotations

import sys
from typing import Any

import requests

# Forzar UTF-8 en stdout para que acentos y símbolos no rompan en Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = "temperature_2m,windspeed_10m,windgusts_10m,freezing_level_height"

BASE_PARAMS: dict[str, Any] = {
    "latitude": 42.65,
    "longitude": 0.55,
    "forecast_days": 2,
    "timezone": "Europe/Madrid",
    "hourly": HOURLY_VARS,
    "models": "best_match",
    "windspeed_unit": "kmh",
}

CASOS: list[tuple[str, int | None]] = [
    ("A", None),
    ("B", 2200),
    ("C", 1500),
    ("D", 3000),
]


def call_openmeteo(elev: int | None) -> tuple[dict, dict]:
    """Llamada plana sin caché. Devuelve (payload_json, response_headers)."""
    params = dict(BASE_PARAMS)
    if elev is not None:
        params["elevation"] = elev
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json(), dict(r.headers)


def slice_dia_1(times: list[str]) -> slice:
    """Devuelve slice de las horas pertenecientes al primer día calendario."""
    primer_dia = times[0][:10]
    n = sum(1 for t in times if t.startswith(primer_dia))
    return slice(0, n)


def metricas_dia_1(payload: dict) -> dict[str, Any]:
    h = payload["hourly"]
    sl = slice_dia_1(h["time"])

    temps = [v for v in h["temperature_2m"][sl] if v is not None]
    winds = [v for v in h["windspeed_10m"][sl] if v is not None]
    gusts = [v for v in h["windgusts_10m"][sl] if v is not None]
    fls = [v for v in h["freezing_level_height"][sl] if v is not None]

    return {
        "elev_api": payload.get("elevation"),
        "temp_max": max(temps) if temps else None,
        "viento_medio": sum(winds) / len(winds) if winds else None,
        "rafaga_max": max(gusts) if gusts else None,
        "freezing_level": sum(fls) / len(fls) if fls else None,
        "generationtime_ms": payload.get("generationtime_ms"),
    }


def fmt(v: Any, prec: int = 2) -> str:
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:.{prec}f}"
    return str(v)


def main() -> None:
    resultados = []
    headers_por_caso: dict[str, dict] = {}

    for nombre, elev in CASOS:
        payload, headers = call_openmeteo(elev)
        m = metricas_dia_1(payload)
        m["caso"] = nombre
        m["elev_pedida"] = elev
        resultados.append(m)
        headers_por_caso[nombre] = headers

    # ---- Tabla comparativa ----
    print()
    print(
        f"{'Caso':<5} {'elev_pedida':<12} {'elev_API':<10} "
        f"{'temp_max_d1':<12} {'viento_medio_d1':<16} "
        f"{'rafaga_max_d1':<14} {'freezing_level_d1':<18}"
    )
    print("-" * 92)
    for r in resultados:
        print(
            f"{r['caso']:<5} "
            f"{fmt(r['elev_pedida'], 0):<12} "
            f"{fmt(r['elev_api'], 1):<10} "
            f"{fmt(r['temp_max']):<12} "
            f"{fmt(r['viento_medio']):<16} "
            f"{fmt(r['rafaga_max']):<14} "
            f"{fmt(r['freezing_level'], 1):<18}"
        )

    # ---- Diferencias vs caso A ----
    base = resultados[0]
    print()
    print("Diferencias respecto a caso A (sin elevation):")
    for r in resultados[1:]:
        d_t = (
            None
            if r["temp_max"] is None or base["temp_max"] is None
            else r["temp_max"] - base["temp_max"]
        )
        d_w = (
            None
            if r["viento_medio"] is None or base["viento_medio"] is None
            else r["viento_medio"] - base["viento_medio"]
        )
        d_t_s = "n/a" if d_t is None else f"{d_t:+.2f} °C"
        d_w_s = "n/a" if d_w is None else f"{d_w:+.2f} km/h"
        print(
            f"  {r['caso']} (elev_pedida={fmt(r['elev_pedida'], 0)}): "
            f"diff_temp_max_d1={d_t_s:<10}   diff_viento_medio_d1={d_w_s}"
        )

    # ---- Veredicto ----
    temps = [r["temp_max"] for r in resultados if r["temp_max"] is not None]
    winds = [r["viento_medio"] for r in resultados if r["viento_medio"] is not None]
    elevs_api = [r["elev_api"] for r in resultados]

    UMBRAL = 0.1
    temp_cambia = (max(temps) - min(temps)) > UMBRAL if len(temps) >= 2 else False
    viento_cambia = (
        (max(winds) - min(winds)) > UMBRAL if len(winds) >= 2 else False
    )

    elev_set = set(elevs_api)
    if len(elev_set) == 1:
        elev_desc = f"valor único = {elevs_api[0]}"
    else:
        pares = ", ".join(
            f"{r['caso']}(pedida={fmt(r['elev_pedida'], 0)})->{fmt(r['elev_api'], 1)}"
            for r in resultados
        )
        elev_desc = f"varía según parámetro: {pares}"

    print()
    print("VEREDICTO:")
    print(
        f"  - temperature_2m responde a elevation: "
        f"{'SÍ' if temp_cambia else 'NO'}"
    )
    print(
        f"  - windspeed_10m responde a elevation:  "
        f"{'SÍ' if viento_cambia else 'NO'}"
    )
    print(f"  - elevation_API es: {elev_desc}")

    # ---- Headers de respuesta (sanity check) ----
    print()
    print("Headers de respuesta Open-Meteo (sanity check, caso A):")
    h_a = headers_por_caso.get("A", {})
    keys_de_interes = ["Server", "Date", "Content-Type", "User-Agent"]
    for k in keys_de_interes:
        v = h_a.get(k)
        print(f"  {k}: {v!r}")
    print()
    print("(Nota: 'User-Agent' es típicamente cabecera de petición, no de "
          "respuesta — si aparece None, es porque Open-Meteo no la devuelve.)")


if __name__ == "__main__":
    main()
