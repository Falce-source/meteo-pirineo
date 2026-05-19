"""Índice de riesgo de tormenta calculado localmente.

ARPEGE no expone un índice operativo; lo construimos a partir de
CAPE (J/kg), weathercode WMO, precipitación (mm/h) y humedad relativa
(%) — ver ADR-006.

Escala 0-3:
    0  atmósfera estable, sin tormenta esperable
    1  inestabilidad moderada, posibles chubascos
    2  tormentas probables
    3  tormentas fuertes / confirmadas por modelo

NaN si faltan tanto CAPE como weathercode.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger("src.tormenta")

# Códigos WMO que confirman tormenta:
#   95 Tormenta moderada/débil sin granizo
#   96 Tormenta con granizo ligero/moderado
#   99 Tormenta con granizo fuerte
WMO_TORMENTA: set[int] = {95, 96, 99}

# Umbrales CAPE (J/kg) → índice base. Calibración orientativa, no
# específica para Pirineo (ver ADR-006).
CAPE_UMBRAL_MODERADO = 500
CAPE_UMBRAL_SIGNIFICATIVO = 1000
CAPE_UMBRAL_ALTO = 2000

# Modificadores
PRECIPITACION_INTENSA = 5.0       # mm/h
HUMEDAD_BAJA = 30.0               # %


def _indice_fila(
    cape: Any,
    weathercode: Any,
    precipitation: Any,
    humedad: Any,
) -> float:
    """Calcula el índice 0-3 para una hora. Devuelve NaN si no es posible."""
    has_wc = weathercode is not None and not pd.isna(weathercode)
    has_cape = cape is not None and not pd.isna(cape)

    if not has_wc and not has_cape:
        return float("nan")

    # Confirmación por modelo: tormenta sí o sí.
    if has_wc and int(weathercode) in WMO_TORMENTA:
        return 3.0

    if not has_cape:
        # weathercode existe pero no es de tormenta y no tenemos CAPE.
        return 0.0

    cape_val = float(cape)
    if cape_val < CAPE_UMBRAL_MODERADO:
        base = 0
    elif cape_val < CAPE_UMBRAL_SIGNIFICATIVO:
        base = 1
    elif cape_val < CAPE_UMBRAL_ALTO:
        base = 2
    else:
        base = 3

    # Precipitación intensa => +1.
    if precipitation is not None and not pd.isna(precipitation):
        if float(precipitation) > PRECIPITACION_INTENSA:
            base += 1

    # Aire seco => -1 (convección menos sostenible).
    if humedad is not None and not pd.isna(humedad):
        if float(humedad) < HUMEDAD_BAJA:
            base -= 1

    return float(max(0, min(3, base)))


def calcular_indice_tormenta(df_horario: pd.DataFrame) -> pd.Series:
    """Devuelve un índice 0-3 por hora basado en CAPE y otros.

    Inputs esperados en ``df_horario`` (cualquier subconjunto):
        - cape (J/kg)
        - weathercode (códigos WMO)
        - precipitation (mm/h)
        - relative_humidity_2m (%)

    Si faltan columnas, se usa una aproximación con las disponibles
    y se loguea un warning. Si faltan TANTO ``cape`` como
    ``weathercode``, todas las filas serán NaN.

    Returns:
        pd.Series con el mismo índice que ``df_horario``, dtype float
        (los enteros 0-3 se devuelven como ``float`` para permitir NaN).
    """
    columnas_input = {"cape", "weathercode", "precipitation", "relative_humidity_2m"}
    faltantes = columnas_input - set(df_horario.columns)
    if faltantes:
        logger.warning(
            "Faltan columnas para índice de tormenta: %s. "
            "Se calcula con las disponibles.",
            sorted(faltantes),
        )

    cape = df_horario.get("cape")
    wc = df_horario.get("weathercode")
    precip = df_horario.get("precipitation")
    hum = df_horario.get("relative_humidity_2m")

    n = len(df_horario.index)
    valores = []
    for i in range(n):
        v_cape = cape.iloc[i] if cape is not None else None
        v_wc = wc.iloc[i] if wc is not None else None
        v_p = precip.iloc[i] if precip is not None else None
        v_h = hum.iloc[i] if hum is not None else None
        valores.append(_indice_fila(v_cape, v_wc, v_p, v_h))

    return pd.Series(valores, index=df_horario.index, name="indice_tormenta")
