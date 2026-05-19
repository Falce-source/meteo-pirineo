"""Tests de ``src.derivadas``.

Verifican el cálculo de variables derivadas y el flag ``_estimada``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.derivadas import (
    LAPSE_RATE_C_PER_M,
    calcular_freezing_level_height,
    enriquecer_con_derivadas,
)


def _df_1h(temp_c: float) -> pd.DataFrame:
    """DataFrame de 1 hora con temperatura constante."""
    idx = pd.date_range(
        "2026-05-19 12:00", periods=1, freq="h", tz="Europe/Madrid"
    )
    idx.name = "time"
    return pd.DataFrame({"temperature_2m": [temp_c]}, index=idx)


def test_freezing_level_height_temp_positiva():
    """T2m=+10 °C a 2200 m → FLH ~ 2200 + 10/0.0065 ≈ 3738 m."""
    df = _df_1h(10.0)
    fl = calcular_freezing_level_height(df, elevacion_zona_m=2200)
    esperado = 2200 + 10.0 / LAPSE_RATE_C_PER_M
    assert fl.iloc[0] == pytest.approx(esperado)
    assert fl.iloc[0] == pytest.approx(3738.46, abs=0.5)


def test_freezing_level_height_temp_negativa():
    """T2m=-5 °C a 2200 m → FLH ~ 2200 - 5/0.0065 ≈ 1431 m."""
    df = _df_1h(-5.0)
    fl = calcular_freezing_level_height(df, elevacion_zona_m=2200)
    esperado = 2200 + (-5.0) / LAPSE_RATE_C_PER_M
    assert fl.iloc[0] == pytest.approx(esperado)
    assert fl.iloc[0] == pytest.approx(1430.77, abs=0.5)


def test_freezing_level_height_serie_horaria():
    """enriquecer_con_derivadas conserva el índice original."""
    idx = pd.date_range(
        "2026-05-19 00:00", periods=24, freq="h", tz="Europe/Madrid"
    )
    idx.name = "time"
    temps = [-2.0 + 0.5 * h for h in range(24)]
    df = pd.DataFrame(
        {
            "temperature_2m": temps,
            "windspeed_10m": [10.0] * 24,
        },
        index=idx,
    )

    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2070)

    # Mismo índice (igualdad exacta).
    assert df_enr.index.equals(df.index)
    # La columna nueva existe y tiene 24 valores no-NaN.
    assert "freezing_level_height" in df_enr.columns
    assert df_enr["freezing_level_height"].notna().all()
    # El cálculo punto-a-punto coincide.
    esperado = [
        2070 + t / LAPSE_RATE_C_PER_M for t in temps
    ]
    assert df_enr["freezing_level_height"].tolist() == pytest.approx(esperado)
    # Variables originales intactas.
    assert df_enr["temperature_2m"].tolist() == temps
    assert df_enr["windspeed_10m"].tolist() == [10.0] * 24


def test_freezing_level_height_flag_estimada():
    """La columna freezing_level_height_estimada existe y es True en toda la franja."""
    df = _df_1h(5.0)
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)

    assert "freezing_level_height_estimada" in df_enr.columns
    serie = df_enr["freezing_level_height_estimada"]
    # Acepta ambos: dtype bool o object con valores True.
    assert bool(serie.iloc[0]) is True
    assert serie.all()
