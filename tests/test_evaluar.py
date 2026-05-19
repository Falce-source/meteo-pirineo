"""Tests de ``src.evaluar``.

Construyen DataFrames sintéticos en memoria, sin red ni fetch real.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest

from src.evaluar import cargar_actividades, evaluar_dia
from src.fetch import HOURLY_VARIABLES, PrevisionMeteo


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def actividades() -> list[dict[str, Any]]:
    """Carga config/actividades.yaml real para usar reglas reales."""
    return cargar_actividades("config/actividades.yaml")


@pytest.fixture
def zona_benasque() -> dict[str, Any]:
    return {
        "id": "benasque",
        "nombre": "Valle de Benasque (Cerler / bajo Aneto)",
        "macizo": "Pirineo aragonés",
        "latitud": 42.65,
        "longitud": 0.55,
        "elevacion_m": 2200,
        "boletin_aludes": {
            "nombre": "AEMET - Pirineo aragonés",
            "url": "https://www.aemet.es/es/eltiempo/prediccion/montana?w=ag0",
        },
    }


def _hourly_df(
    fecha: date,
    valores_por_var: dict[str, list[float]] | None = None,
    valor_default: float = 0.0,
) -> pd.DataFrame:
    """Construye un DataFrame de 24 h para un día, tz Europe/Madrid.

    ``valores_por_var`` permite sobrescribir variables concretas con
    una lista de 24 valores. El resto van a ``valor_default``.
    """
    idx = pd.date_range(
        start=f"{fecha.isoformat()} 00:00",
        periods=24,
        freq="h",
        tz="Europe/Madrid",
    )
    idx.name = "time"
    data = {var: [valor_default] * 24 for var in HOURLY_VARIABLES}
    if valores_por_var:
        for var, vals in valores_por_var.items():
            assert len(vals) == 24, f"{var}: se esperaban 24 valores"
            data[var] = vals
    return pd.DataFrame(data, index=idx)


def _prevision(
    zona: dict[str, Any], df: pd.DataFrame
) -> PrevisionMeteo:
    return PrevisionMeteo(
        zona=zona,
        timestamp_fetch=datetime(2026, 5, 19, 14, 0),
        horario=df,
        metadata={"modelo_solicitado": "meteofrance_arome_france"},
    )


def _actividad(actividades: list[dict], id_: str) -> dict[str, Any]:
    for a in actividades:
        if a["id"] == id_:
            return a
    raise KeyError(id_)


# ---------- Test 1: día tranquilo ----------

def test_semaforo_verde_dia_tranquilo(actividades, zona_benasque):
    """Valores benignos para todas las variables: todo verde."""
    fecha = date(2026, 6, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [15.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [20.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [3500.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)

    for act in actividades:
        ev = evaluar_dia(prev, act, fecha)
        assert ev.semaforo == "VERDE", (
            f"{act['id']}: esperaba VERDE, salió {ev.semaforo}. "
            f"motivos={ev.motivos}"
        )


# ---------- Test 2: viento extremo ----------

def test_semaforo_rojo_viento_extremo(actividades, zona_benasque):
    """Viento 60 km/h sostenido dispara ROJO en skimo, alpinismo_invierno, ciclismo."""
    fecha = date(2026, 1, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [0.0] * 24,
            "windspeed_10m": [60.0] * 24,
            "windgusts_10m": [80.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [2000.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)

    for act_id in ("skimo", "alpinismo_invierno", "ciclismo"):
        act = _actividad(actividades, act_id)
        ev = evaluar_dia(prev, act, fecha)
        assert ev.semaforo == "ROJO", (
            f"{act_id}: esperaba ROJO, salió {ev.semaforo}"
        )
        # Alguna regla de viento debe haber disparado.
        vars_disparadas = {m.variable for m in ev.motivos if m.nivel == "ROJO"}
        assert vars_disparadas & {"windspeed_10m", "windgusts_10m"}, (
            f"{act_id}: no disparó ninguna regla de viento. "
            f"motivos={ev.motivos}"
        )


# ---------- Test 3: franja horaria respetada ----------

def test_franja_horaria_respetada(actividades, zona_benasque):
    """Viento alto solo entre 03-06 (fuera de franja 07-17) NO debe disparar."""
    fecha = date(2026, 1, 15)
    viento = [10.0] * 24
    rafagas = [20.0] * 24
    for h in (3, 4, 5, 6):
        viento[h] = 80.0
        rafagas[h] = 100.0

    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [0.0] * 24,
            "windspeed_10m": viento,
            "windgusts_10m": rafagas,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [2000.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)

    motivos_rojo = [m for m in ev.motivos if m.nivel == "ROJO"]
    assert not motivos_rojo, (
        f"No debería haber motivos ROJO con viento fuera de franja, "
        f"hay: {motivos_rojo}"
    )
    # Tampoco debería haber AMBAR por viento.
    motivos_viento_ambar = [
        m for m in ev.motivos
        if m.nivel == "AMBAR" and m.variable in {"windspeed_10m", "windgusts_10m"}
    ]
    assert not motivos_viento_ambar


# ---------- Test 4: franja específica (regla derivada -> pendiente) ----------

def test_franja_especifica_override(actividades, zona_benasque):
    """alpinismo_estival usa indice_tormenta (derivada).

    En Semana 2 NO se evalúa; debe aparecer como aviso pendiente y
    no romper la evaluación.
    """
    fecha = date(2026, 7, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [18.0] * 24,
            "windspeed_10m": [15.0] * 24,
            "windgusts_10m": [25.0] * 24,
            "cloudcover": [40.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [3500.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)

    alp = _actividad(actividades, "alpinismo_estival")
    ev = evaluar_dia(prev, alp, fecha)

    # Debe haber un aviso pendiente que mencione la regla de tormenta.
    avisos_pendientes = [
        a for a in ev.avisos if "pendiente" in a.lower()
    ]
    assert any(
        "tormenta" in a.lower() for a in avisos_pendientes
    ), f"esperaba aviso pendiente por indice_tormenta. avisos={ev.avisos}"
    # La evaluación no debe romperse; semáforo válido.
    assert ev.semaforo in {"VERDE", "AMBAR", "ROJO", "SIN_DATOS"}


# ---------- Test 5: informativo no afecta semáforo ----------

def test_informativo_no_afecta_semaforo(actividades, zona_benasque):
    """Cero térmico bajo en regla informativa: aparece pero no sube el color."""
    fecha = date(2026, 3, 20)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [0.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [1500.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)

    alp_inv = _actividad(actividades, "alpinismo_invierno")
    ev = evaluar_dia(prev, alp_inv, fecha)

    info = [m for m in ev.motivos if m.nivel == "INFORMATIVO"]
    assert info, f"esperaba al menos un motivo INFORMATIVO. motivos={ev.motivos}"
    assert any(m.variable == "freezing_level_height" for m in info)

    # El semáforo no debe ser ROJO ni AMBAR por culpa de informativos.
    niveles_no_info = {m.nivel for m in ev.motivos if m.nivel != "INFORMATIVO"}
    if not niveles_no_info:
        assert ev.semaforo == "VERDE"


# ---------- Test 6: aviso de aludes según mes ----------

def test_aviso_aludes_solo_en_invierno(actividades, zona_benasque):
    """Skimo en julio: sin aviso de aludes. En enero: con aviso."""
    skimo = _actividad(actividades, "skimo")

    # Día tranquilo, mismas variables base, dos fechas distintas.
    base_vals = {
        "temperature_2m": [5.0] * 24,
        "windspeed_10m": [10.0] * 24,
        "windgusts_10m": [20.0] * 24,
        "cloudcover": [30.0] * 24,
        "precipitation": [0.0] * 24,
        "freezing_level_height": [2500.0] * 24,
    }

    fecha_jul = date(2026, 7, 10)
    prev_jul = _prevision(zona_benasque, _hourly_df(fecha_jul, base_vals))
    ev_jul = evaluar_dia(prev_jul, skimo, fecha_jul)
    avisos_aludes_jul = [a for a in ev_jul.avisos if "aludes" in a.lower()]
    assert not avisos_aludes_jul, (
        f"julio no debería tener aviso de aludes: {avisos_aludes_jul}"
    )

    fecha_ene = date(2026, 1, 10)
    prev_ene = _prevision(zona_benasque, _hourly_df(fecha_ene, base_vals))
    ev_ene = evaluar_dia(prev_ene, skimo, fecha_ene)
    avisos_aludes_ene = [a for a in ev_ene.avisos if "aludes" in a.lower()]
    assert avisos_aludes_ene, (
        f"enero debería tener aviso de aludes. avisos={ev_ene.avisos}"
    )


# ---------- Test 7: variable derivada queda pendiente ----------

def test_variable_derivada_pendiente(actividades, zona_benasque):
    """snowfall_48h_previas no implementada: aviso pendiente, sin romper."""
    fecha = date(2026, 2, 10)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [-5.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [1800.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)

    pendientes = [a for a in ev.avisos if "pendiente" in a.lower()]
    assert any(
        "nevada reciente" in a.lower() or "snowfall_48h" in a.lower()
        for a in pendientes
    ), f"esperaba aviso pendiente por snowfall_48h_previas. avisos={ev.avisos}"
    # La regla no debe figurar en motivos (no se evalúa).
    assert not any(
        m.variable == "snowfall_48h_previas" for m in ev.motivos
    )


# ---------- Test 8: peor componente determina ----------

def test_peor_componente_determina(actividades, zona_benasque):
    """Si una regla dispara AMBAR y otra ROJO, el semáforo final es ROJO."""
    fecha = date(2026, 1, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [0.0] * 24,
            # Viento medio 35 km/h: ámbar skimo (>30), no rojo (<50).
            "windspeed_10m": [35.0] * 24,
            # Ráfaga max 80 km/h: rojo skimo (>70).
            "windgusts_10m": [80.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [2000.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)
    skimo = _actividad(actividades, "skimo")

    ev = evaluar_dia(prev, skimo, fecha)
    niveles = {m.nivel for m in ev.motivos}
    assert "ROJO" in niveles
    assert "AMBAR" in niveles
    assert ev.semaforo == "ROJO"


# ---------- Test 9: datos_clave se rellenan ----------

def test_datos_clave_se_rellenan(actividades, zona_benasque):
    """Tras evaluar, datos_clave contiene una entrada por regla evaluada."""
    fecha = date(2026, 1, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [-5.0] * 24,
            "windspeed_10m": [25.0] * 24,
            "windgusts_10m": [40.0] * 24,
            "cloudcover": [50.0] * 24,
            "precipitation": [0.0] * 24,
            "freezing_level_height": [2000.0] * 24,
        },
    )
    prev = _prevision(zona_benasque, df)
    skimo = _actividad(actividades, "skimo")

    ev = evaluar_dia(prev, skimo, fecha)

    # skimo evalúa: windspeed_10m_mean, windgusts_10m_max, cloudcover_mean,
    # temperature_2m_min. snowfall_48h_previas es derivada (no entra).
    esperadas = {
        "windspeed_10m_mean",
        "windgusts_10m_max",
        "cloudcover_mean",
        "temperature_2m_min",
    }
    assert esperadas.issubset(set(ev.datos_clave.keys())), (
        f"faltan claves: {esperadas - set(ev.datos_clave.keys())}. "
        f"presentes: {ev.datos_clave.keys()}"
    )

    # Valor agregado coherente con el input (franja 07-17, valores constantes).
    assert ev.datos_clave["windspeed_10m_mean"] == pytest.approx(25.0)
    assert ev.datos_clave["windgusts_10m_max"] == pytest.approx(40.0)
    assert ev.datos_clave["temperature_2m_min"] == pytest.approx(-5.0)
