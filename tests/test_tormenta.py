"""Tests del índice de tormenta calculado localmente."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.tormenta import calcular_indice_tormenta


def _df(
    cape: float | None = 0.0,
    weathercode: int | None = 1,
    precipitation: float | None = 0.0,
    humedad: float | None = 50.0,
) -> pd.DataFrame:
    """DataFrame de 1 hora con los valores indicados."""
    idx = pd.date_range(
        "2026-07-15 14:00", periods=1, freq="h", tz="Europe/Madrid"
    )
    idx.name = "time"
    data: dict[str, list] = {}
    if cape is not None:
        data["cape"] = [cape]
    if weathercode is not None:
        data["weathercode"] = [weathercode]
    if precipitation is not None:
        data["precipitation"] = [precipitation]
    if humedad is not None:
        data["relative_humidity_2m"] = [humedad]
    return pd.DataFrame(data, index=idx)


def _scalar(serie: pd.Series) -> float:
    """Primer valor de la serie como float (o NaN)."""
    return float(serie.iloc[0])


def test_indice_cero_atmosfera_estable():
    df = _df(cape=200, weathercode=1, precipitation=0, humedad=60)
    assert _scalar(calcular_indice_tormenta(df)) == 0.0


def test_indice_uno_cape_moderado():
    df = _df(cape=700, weathercode=1, precipitation=0, humedad=60)
    assert _scalar(calcular_indice_tormenta(df)) == 1.0


def test_indice_dos_cape_significativo():
    df = _df(cape=1500, weathercode=1, precipitation=0, humedad=60)
    assert _scalar(calcular_indice_tormenta(df)) == 2.0


def test_indice_tres_cape_alto():
    df = _df(cape=2500, weathercode=1, precipitation=0, humedad=60)
    assert _scalar(calcular_indice_tormenta(df)) == 3.0


def test_indice_tres_por_weathercode():
    """CAPE bajo pero weathercode 95 (tormenta confirmada) → 3."""
    df = _df(cape=300, weathercode=95, precipitation=0, humedad=60)
    assert _scalar(calcular_indice_tormenta(df)) == 3.0


def test_indice_sube_por_precipitacion_intensa():
    """CAPE 800 (base 1) + 7 mm/h → 2."""
    df = _df(cape=800, weathercode=1, precipitation=7, humedad=60)
    assert _scalar(calcular_indice_tormenta(df)) == 2.0


def test_indice_baja_por_aire_seco():
    """CAPE 800 (base 1) + humedad 20% → 0."""
    df = _df(cape=800, weathercode=1, precipitation=0, humedad=20)
    assert _scalar(calcular_indice_tormenta(df)) == 0.0


def test_indice_nan_si_falta_cape_y_weathercode():
    """Sin CAPE ni weathercode → NaN."""
    df = _df(cape=None, weathercode=None, precipitation=0, humedad=60)
    val = _scalar(calcular_indice_tormenta(df))
    assert math.isnan(val)
