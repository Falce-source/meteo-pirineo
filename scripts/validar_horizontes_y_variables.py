"""Validar horizonte temporal y disponibilidad de variables por modelo.

Script desechable de exploración. NO usar en producción.

Ejecutar desde la raíz del repo:
    python scripts/validar_horizontes_y_variables.py
"""

from __future__ import annotations

import sys
from typing import Any

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://api.open-meteo.com/v1/forecast"

VARIABLES: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "precipitation_probability",
    "weathercode",
    "snowfall",
    "cloudcover",
    "windspeed_10m",
    "windgusts_10m",
    "winddirection_10m",
    "cape",
    "freezing_level_height",
]

MODELOS: list[str] = [
    "meteofrance_arome_france",
    "meteofrance_arpege_europe",
]

PUNTO: dict[str, Any] = {
    "latitude": 42.65,
    "longitude": 0.55,
    "elevation": 2200,
}


def call(modelo: str) -> dict[str, Any]:
    params = {
        **PUNTO,
        "forecast_days": 5,
        "timezone": "Europe/Madrid",
        "hourly": ",".join(VARIABLES),
        "models": modelo,
        "windspeed_unit": "kmh",
    }
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def analizar(payload: dict) -> dict[str, Any]:
    hourly = payload.get("hourly") or {}
    times: list[str] = hourly.get("time") or []
    n_total = len(times)

    # Para cada índice horario, ¿hay al menos un dato no-nulo?
    fila_tiene_dato: list[bool] = []
    for i in range(n_total):
        tiene = False
        for var in VARIABLES:
            vals = hourly.get(var) or []
            if i < len(vals) and vals[i] is not None:
                tiene = True
                break
        fila_tiene_dato.append(tiene)

    primer_idx = next((i for i, ok in enumerate(fila_tiene_dato) if ok), None)
    ultimo_idx = next(
        (i for i in range(n_total - 1, -1, -1) if fila_tiene_dato[i]),
        None,
    )
    n_con_datos = sum(1 for ok in fila_tiene_dato if ok)

    if primer_idx is None or ultimo_idx is None:
        horizonte_h = 0
        primer_time = None
        ultimo_time = None
    else:
        primer_time = times[primer_idx]
        ultimo_time = times[ultimo_idx]
        horizonte_h = ultimo_idx - primer_idx + 1

    # Cobertura por variable sobre las filas con datos.
    cobertura: dict[str, float] = {}
    indices_con_dato = [i for i, ok in enumerate(fila_tiene_dato) if ok]
    base = len(indices_con_dato)
    for var in VARIABLES:
        vals = hourly.get(var) or []
        if base == 0:
            cobertura[var] = 0.0
            continue
        ok = sum(
            1
            for i in indices_con_dato
            if i < len(vals) and vals[i] is not None
        )
        cobertura[var] = 100.0 * ok / base

    return {
        "n_total": n_total,
        "n_con_datos": n_con_datos,
        "primer_idx": primer_idx,
        "ultimo_idx": ultimo_idx,
        "primer_time": primer_time,
        "ultimo_time": ultimo_time,
        "horizonte_h": horizonte_h,
        "cobertura": cobertura,
    }


def imprimir_tabla(modelo: str, a: dict[str, Any]) -> None:
    print()
    print(f"==== {modelo} ====")
    print(f"Primera hora con datos: {a['primer_time']}")
    print(f"Última hora con datos:  {a['ultimo_time']}")
    print(f"Horizonte efectivo:     {a['horizonte_h']} horas")
    print(f"Total horas pedidas:    {a['n_total']}")
    print(f"Horas con datos:        {a['n_con_datos']}")
    cobertura_total = (
        100.0 * a["n_con_datos"] / a["n_total"] if a["n_total"] else 0.0
    )
    print(f"Cobertura:              {cobertura_total:.1f}%")
    print()
    print("Variables (cobertura sobre las "
          f"{a['n_con_datos']} horas con al menos un dato):")
    for var in VARIABLES:
        pct = a["cobertura"][var]
        marcador = "    <-- NO DISPONIBLE" if pct == 0.0 else ""
        print(f"  {var:<28}{pct:>5.1f}%{marcador}")


def main() -> None:
    resultados: dict[str, dict[str, Any]] = {}

    for modelo in MODELOS:
        payload = call(modelo)
        a = analizar(payload)
        resultados[modelo] = a
        imprimir_tabla(modelo, a)

    # ---- Análisis para combinación de modelos ----
    a1 = resultados[MODELOS[0]]
    a2 = resultados[MODELOS[1]]

    # Solapamiento temporal: por strings ISO (formato fijo "YYYY-MM-DDTHH:MM").
    inicio = (
        max(a1["primer_time"], a2["primer_time"])
        if a1["primer_time"] and a2["primer_time"]
        else None
    )
    fin = (
        min(a1["ultimo_time"], a2["ultimo_time"])
        if a1["ultimo_time"] and a2["ultimo_time"]
        else None
    )

    def parse_dt(s: str):
        # 'YYYY-MM-DDTHH:MM' -> tupla comparable; usamos datetime para horas.
        from datetime import datetime
        return datetime.fromisoformat(s)

    if inicio and fin and inicio <= fin:
        horas_solape = int(
            (parse_dt(fin) - parse_dt(inicio)).total_seconds() // 3600
        ) + 1
    else:
        horas_solape = 0

    DISPONIBLE = 0.0  # umbral estricto: >0% se considera disponible
    vars_arome = {
        v for v in VARIABLES if a1["cobertura"][v] > DISPONIBLE
    }
    vars_arpege = {
        v for v in VARIABLES if a2["cobertura"][v] > DISPONIBLE
    }
    solo_arome = sorted(vars_arome - vars_arpege)
    solo_arpege = sorted(vars_arpege - vars_arome)
    en_ambos = sorted(vars_arome & vars_arpege)
    en_ninguno = sorted(set(VARIABLES) - vars_arome - vars_arpege)

    print()
    print("ANÁLISIS PARA COMBINACIÓN DE MODELOS:")
    if inicio and fin and horas_solape > 0:
        print(
            f"- Solapamiento temporal AROME ∩ ARPEGE: "
            f"{inicio} a {fin} ({horas_solape} horas)"
        )
    else:
        print("- Solapamiento temporal AROME ∩ ARPEGE: ninguno")
    print(f"- Variables solo en AROME:     {solo_arome}")
    print(f"- Variables solo en ARPEGE:    {solo_arpege}")
    print(f"- Variables en ambos:          {en_ambos}")
    print(f"- Variables en ninguno:        {en_ninguno}")


if __name__ == "__main__":
    main()
