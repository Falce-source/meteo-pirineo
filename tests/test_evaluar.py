"""Tests de ``src.evaluar``.

Construyen DataFrames sintéticos en memoria, sin red ni fetch real.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest

from src.derivadas import enriquecer_con_derivadas
from src.evaluar import cargar_actividades, calcular_ventanas_dia, evaluar_dia
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
        if ev is None:
            # Actividad fuera de temporada en esta fecha (ADR-010).
            continue
        assert ev.semaforo == "VERDE", (
            f"{act['id']}: esperaba VERDE, salió {ev.semaforo}. "
            f"motivos={ev.motivos}"
        )


# ---------- Test 2: viento extremo ----------

def test_semaforo_rojo_viento_extremo(actividades, zona_benasque):
    """Viento 60 km/h sostenido dispara ROJO en skimo, alpinismo_invierno, ciclismo."""
    # Abril cae en los meses_activos de las tres actividades probadas
    # (skimo 11-5, alp_inv 11-6, ciclismo 3-11).
    fecha = date(2026, 4, 15)
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


# ---------- Test 4: franja específica con tormenta calculada (Semana 4) ----------

def test_franja_especifica_override(actividades, zona_benasque):
    """Semana 4: ``indice_tormenta`` se evalúa, ya no es aviso pendiente.

    Con CAPE bajo, la regla con franja_especifica se procesa pero no
    dispara, y no aparece aviso pendiente para indice_tormenta.
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
            "relative_humidity_2m": [50.0] * 24,
            "cape": [200.0] * 24,  # bajo → indice 0
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    alp = _actividad(actividades, "alpinismo_estival")
    ev = evaluar_dia(prev, alp, fecha)

    # YA NO debe aparecer indice_tormenta como aviso pendiente.
    pendientes_tormenta = [
        a for a in ev.avisos
        if "pendiente" in a.lower() and "tormenta" in a.lower()
    ]
    assert not pendientes_tormenta, (
        f"indice_tormenta ya no debe ser pendiente. avisos={ev.avisos}"
    )

    # Con CAPE bajo, la regla no dispara.
    motivos_tormenta = [
        m for m in ev.motivos if m.variable == "indice_tormenta"
    ]
    assert not motivos_tormenta

    # La evaluación sigue siendo válida.
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
    """Aviso de aludes solo dentro de MESES_AVISO_ALUDES (11-5), incluso
    si la actividad sigue activa fuera de esa ventana.

    Caso 1: alpinismo_invierno en junio. Activo (meses_activos incluye 6)
    pero junio no está en aludes → no aviso.
    Caso 2: skimo en enero. Activo y en aludes month → aviso.
    """
    base_vals = {
        "temperature_2m": [5.0] * 24,
        "windspeed_10m": [10.0] * 24,
        "windgusts_10m": [20.0] * 24,
        "cloudcover": [30.0] * 24,
        "precipitation": [0.0] * 24,
        "freezing_level_height": [2500.0] * 24,
    }

    # Caso 1: actividad activa en junio, no aludes month.
    alp_inv = _actividad(actividades, "alpinismo_invierno")
    fecha_jun = date(2026, 6, 10)
    prev_jun = _prevision(zona_benasque, _hourly_df(fecha_jun, base_vals))
    ev_jun = evaluar_dia(prev_jun, alp_inv, fecha_jun)
    assert ev_jun is not None, "alpinismo_invierno debería estar activo en junio"
    avisos_aludes_jun = [a for a in ev_jun.avisos if "aludes" in a.lower()]
    assert not avisos_aludes_jun, (
        f"junio no debería tener aviso de aludes: {avisos_aludes_jun}"
    )

    # Caso 2: actividad activa en enero, aludes month.
    skimo = _actividad(actividades, "skimo")
    fecha_ene = date(2026, 1, 10)
    prev_ene = _prevision(zona_benasque, _hourly_df(fecha_ene, base_vals))
    ev_ene = evaluar_dia(prev_ene, skimo, fecha_ene)
    assert ev_ene is not None, "skimo debería estar activo en enero"
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


# ---------- Test 10: FLH dispara AMBAR y se marca estimada (Semana 2.5) ----------

def test_freezing_level_height_dispara_ambar_y_marca_estimada(
    actividades, zona_benasque
):
    """T2m=-10°C a 2200m → FLH calc ~661 m < 2500 m → AMBAR alpinismo_estival.

    El motivo correspondiente debe llevar estimada=True porque el FLH
    proviene de src.derivadas y no del modelo.
    """
    fecha = date(2026, 7, 15)
    df = _hourly_df(
        fecha,
        {
            # Frío constante para forzar FLH bajo.
            "temperature_2m": [-10.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            # freezing_level_height venía como columna (de fetch); el
            # enriquecimiento la sobrescribe.
            "freezing_level_height": [float("nan")] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    alp_est = _actividad(actividades, "alpinismo_estival")
    ev = evaluar_dia(prev, alp_est, fecha)

    motivos_flh = [
        m for m in ev.motivos
        if m.variable == "freezing_level_height" and m.nivel == "AMBAR"
    ]
    assert motivos_flh, (
        f"esperaba motivo AMBAR para freezing_level_height. "
        f"motivos={ev.motivos}"
    )
    motivo = motivos_flh[0]
    assert motivo.estimada is True
    assert motivo.op == "<"
    assert motivo.umbral_disparado == pytest.approx(2500.0)
    # FLH calculado debe estar muy por debajo del umbral (~661 m).
    assert motivo.valor_observado < 1000


# ---------- Tests Semana 4: regla de tormenta integrada ----------

def test_regla_tormenta_dispara_rojo_alpinismo_estival(
    actividades, zona_benasque
):
    """CAPE alto a las 15:00 (dentro de franja_especifica 13-20)
    debe disparar ROJO en alpinismo_estival por indice_tormenta>=2."""
    fecha = date(2026, 7, 15)
    cape_serie = [200.0] * 24
    for h in range(13, 21):  # 13:00 a 20:00
        cape_serie[h] = 2200.0  # CAPE alto → indice 3
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [18.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [40.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [55.0] * 24,
            "cape": cape_serie,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    alp_est = _actividad(actividades, "alpinismo_estival")
    ev = evaluar_dia(prev, alp_est, fecha)

    motivos_tormenta_rojo = [
        m for m in ev.motivos
        if m.variable == "indice_tormenta" and m.nivel == "ROJO"
    ]
    assert motivos_tormenta_rojo, (
        f"esperaba motivo ROJO por indice_tormenta. motivos={ev.motivos}"
    )
    assert ev.semaforo == "ROJO"
    # La regla viene de variable derivada → motivo marcado como estimado.
    assert motivos_tormenta_rojo[0].estimada is True


def test_regla_tormenta_no_dispara_en_franja_matinal_estival(
    actividades, zona_benasque
):
    """CAPE alto solo a las 09:00 (fuera de franja_especifica 13-20 de
    alpinismo_estival) NO debe disparar ROJO para alpinismo_estival,
    pero SÍ para trail (franja 7-17 que incluye 09:00)."""
    fecha = date(2026, 7, 15)
    cape_serie = [200.0] * 24
    cape_serie[9] = 2200.0  # solo a las 09:00
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [18.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [40.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [55.0] * 24,
            "cape": cape_serie,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    # Alpinismo estival: franja_especifica [13, 20] -> NO debe disparar.
    alp_est = _actividad(actividades, "alpinismo_estival")
    ev_est = evaluar_dia(prev, alp_est, fecha)
    motivos_tormenta_est = [
        m for m in ev_est.motivos if m.variable == "indice_tormenta"
    ]
    assert not motivos_tormenta_est, (
        f"alpinismo_estival no debería disparar fuera de franja específica. "
        f"motivos={ev_est.motivos}"
    )

    # Trail: franja_horaria [7, 17] (incluye 09:00) -> SÍ debe disparar.
    trail = _actividad(actividades, "trail")
    ev_trail = evaluar_dia(prev, trail, fecha)
    motivos_tormenta_trail = [
        m for m in ev_trail.motivos if m.variable == "indice_tormenta"
    ]
    assert motivos_tormenta_trail, (
        f"trail debería disparar a las 09:00 (dentro de su franja). "
        f"motivos={ev_trail.motivos}"
    )
    assert motivos_tormenta_trail[0].nivel == "ROJO"


# ---------- Tests Semana 5: mejor/peor ventana del día (ADR-007) ----------

def test_mejor_ventana_dia_homogeneo(actividades, zona_benasque):
    """Día con condiciones constantes: todas las sub-ventanas mismo
    semáforo → es_homogenea=True, ventanas.homogenea poblada (ADR-009)."""
    # Febrero está en meses_activos de skimo (11-5).
    fecha = date(2026, 2, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [15.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [20.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [200.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)

    assert ev.ventanas is not None
    assert ev.ventanas.es_homogenea is True
    assert ev.ventanas.homogenea is not None
    assert ev.ventanas.homogenea.semaforo == "VERDE"
    assert ev.ventanas.mejor is None
    assert ev.ventanas.peor is None
    assert ev.ventanas.duracion_h == 4  # skimo declara ventana_minima_h=4


def test_mejor_ventana_destaca_subfranja_favorable(actividades, zona_benasque):
    """Viento 60 km/h solo 14-17h (fuera del rango VERDE matinal).
    Skimo (ventana 4h): mejor ventana matinal VERDE, peor incluye horas
    de viento con motivos disparados.
    """
    fecha = date(2026, 2, 15)
    viento = [10.0] * 24
    rafagas = [20.0] * 24
    for h in (14, 15, 16, 17):
        viento[h] = 60.0
        rafagas[h] = 80.0
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [0.0] * 24,
            "windspeed_10m": viento,
            "windgusts_10m": rafagas,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)

    assert ev.ventanas is not None
    mejor = ev.ventanas.mejor
    peor = ev.ventanas.peor
    assert mejor is not None and peor is not None

    # La mejor ventana debe ser VERDE (matinal, sin viento).
    assert mejor.semaforo == "VERDE", (
        f"mejor ventana esperaba VERDE, salió {mejor.semaforo}"
    )
    # Empate temprano: la ventana más temprana es 07:00-11:00.
    assert mejor.inicio == 7
    assert mejor.fin == 11

    # La peor ventana debe incluir alguna hora con viento alto y disparar
    # al menos motivo ROJO.
    assert peor.semaforo == "ROJO", (
        f"peor ventana esperaba ROJO, salió {peor.semaforo}"
    )
    # La peor ventana debe acabar más tarde que la mejor.
    assert peor.fin > mejor.fin


def test_peor_ventana_es_la_mas_estricta(actividades, zona_benasque):
    """Dos sub-ventanas con motivos diferentes: ROJO > AMBAR. Trail (ventana 2h)."""
    fecha = date(2026, 6, 15)
    # Construir un día con dos focos: AMBAR en mediodía (lluvia ligera),
    # ROJO en tarde (lluvia intensa).
    precip = [0.0] * 24
    for h in (11, 12):
        precip[h] = 6.0   # > umbral ámbar 5 mm/h (trail) → AMBAR
    for h in (15, 16):
        precip[h] = 20.0  # bien por encima de cualquier umbral
    temps = [20.0] * 24
    for h in (15, 16):
        temps[h] = 36.0   # > umbral rojo 35 °C trail → ROJO
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": temps,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": precip,
            "relative_humidity_2m": [55.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    trail = _actividad(actividades, "trail")
    ev = evaluar_dia(prev, trail, fecha)

    assert ev.ventanas is not None
    assert ev.ventanas.peor is not None
    # La peor debe contener una de las horas ROJO (15-16) y disparar
    # motivo de temperature_2m o precipitation con nivel ROJO.
    peor = ev.ventanas.peor
    assert peor.semaforo == "ROJO"
    niveles = {m.nivel for m in peor.motivos}
    assert "ROJO" in niveles


def test_ventana_no_se_calcula_si_no_declarada(actividades, zona_benasque):
    """Actividad sin ventana_minima_h: ev.ventanas.mejor/peor son None."""
    # Febrero está en meses_activos de skimo (11-5).
    fecha = date(2026, 2, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [15.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [20.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    # Construimos un fake actividad sin ventana_minima_h a partir de skimo.
    skimo = _actividad(actividades, "skimo")
    skimo_sin_ventana = {k: v for k, v in skimo.items() if k != "ventana_minima_h"}

    ev = evaluar_dia(prev, skimo_sin_ventana, fecha)
    assert ev.ventanas is not None  # dataclass siempre presente
    assert ev.ventanas.mejor is None
    assert ev.ventanas.peor is None
    assert ev.ventanas.duracion_h == 0


def test_ventana_mayor_que_franja_caso_degenerado(actividades, zona_benasque):
    """ventana_minima_h=12 sobre franja [7,17] (11 h): única ventana
    expuesta como homogenea (ADR-009)."""
    fecha = date(2026, 6, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [15.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [20.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    # Construimos un fake actividad: trail con ventana_minima_h=12.
    trail = _actividad(actividades, "trail")
    trail_largo = dict(trail)
    trail_largo["ventana_minima_h"] = 12

    v = calcular_ventanas_dia(prev, trail_largo, fecha)
    assert v.es_homogenea is True
    assert v.homogenea is not None
    assert v.homogenea.inicio == 7
    assert v.mejor is None
    assert v.peor is None
    assert v.duracion_h == 12


def test_ventana_empate_prefiere_temprana(actividades, zona_benasque):
    """Día homogéneo: se expone una única ventana (la más temprana) y
    no se duplica como mejor/peor (ADR-009)."""
    # Febrero está en meses_activos de skimo (11-5).
    fecha = date(2026, 2, 15)
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [15.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [20.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)

    # Empate total: skimo ventana_minima_h=4, franja [7,17] -> 7 ventanas
    # posibles (start 7..13), todas VERDE. La política de Semana 5+ las
    # expone como homogenea sobre la más temprana (inicio=7).
    assert ev.ventanas is not None
    assert ev.ventanas.es_homogenea is True
    assert ev.ventanas.homogenea is not None
    assert ev.ventanas.homogenea.inicio == 7


# ---------- Tests ADR-009: desempate por menor solape ----------

def test_ventana_desempate_por_menor_solape(actividades, zona_benasque):
    """Múltiples sub-ventanas AMBAR y varias ROJO: el par seleccionado
    debe minimizar el solape temporal, no escoger la más temprana sin más.

    Setup: alpinismo_invierno (ventana=6h, franja [7,17]) →
    starts 7..12 = 6 sub-ventanas. Baseline AMBAR por cloudcover=75 (>70).
    Spike ROJO por windgusts=65 (>60 alpinismo_invierno) a las 14:00 →
    afecta a windows cuyo rango inclusive contiene la hora 14.

    Pares candidatos (mejor 7-13, 8-14 AMBAR vs peor 9-15, 10-16, 11-17,
    12-18 ROJO) y sus solapes; min solape = 1h, par (7-13, 12-18).
    """
    fecha = date(2026, 1, 15)
    rafagas = [20.0] * 24
    rafagas[14] = 65.0  # única hora con ROJO trigger
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [0.0] * 24,
            "windspeed_10m": [20.0] * 24,
            "windgusts_10m": rafagas,
            "cloudcover": [75.0] * 24,  # AMBAR base (>70 alpinismo_invierno)
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
            "freezing_level_height": [float("nan")] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    alp_inv = _actividad(actividades, "alpinismo_invierno")
    v = calcular_ventanas_dia(prev, alp_inv, fecha)

    assert v.es_homogenea is False
    assert v.mejor is not None and v.peor is not None
    assert v.mejor.semaforo == "AMBAR"
    assert v.peor.semaforo == "ROJO"
    # El par con menor solape es (7-13, 12-18) = 1h.
    assert v.mejor.inicio == 7
    assert v.mejor.fin == 13
    assert v.peor.inicio == 12
    assert v.peor.fin == 18

    def solape(a, b):
        return max(0, min(a.fin, b.fin) - max(a.inicio, b.inicio))

    assert solape(v.mejor, v.peor) == 1


def test_ventana_solape_total_se_acepta_si_es_lo_unico(zona_benasque):
    """Cuando solo hay una sub-ventana en cada categoría y se solapan
    forzosamente, el algoritmo las devuelve igualmente — no None.

    Actividad ad-hoc: franja [10, 16] (7h), ventana=6h → 2 sub-ventanas.
    [10,15] (inclusive) → fin exclusivo 16; [11,16] → fin exclusivo 17.
    Solape forzado = 5h.

    AMBAR por rafagas[10]=50; VERDE por nada; ROJO por rafagas[16]=80.
    Como solo hay 2 ventanas y ambas comparten 11..15, la 1ª es AMBAR
    (sin spike rojo) y la 2ª es ROJO (incluye hora 16). El par es único.
    """
    fecha = date(2026, 6, 15)
    actividad_custom = {
        "id": "test_largo",
        "nombre": "Test ad-hoc",
        "franja_horaria": [10, 16],
        "ventana_minima_h": 6,
        "requiere_aviso_aludes": False,
        "reglas": [
            {
                "variable": "windgusts_10m",
                "agg": "max",
                "op": ">",
                "rojo": 60,
                "ambar": 30,
                "unidad": "km/h",
                "descripcion": "Ráfagas",
            },
        ],
    }
    rafagas = [0.0] * 24
    rafagas[10] = 50.0   # AMBAR para [10,15], NO incluido en [11,16]
    rafagas[16] = 80.0   # ROJO para [11,16], NO incluido en [10,15]
    df = _hourly_df(
        fecha,
        {
            "temperature_2m": [15.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": rafagas,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    v = calcular_ventanas_dia(prev, actividad_custom, fecha)

    assert v.es_homogenea is False
    assert v.mejor is not None
    assert v.peor is not None
    assert v.mejor.semaforo == "AMBAR"
    assert v.peor.semaforo == "ROJO"
    # Solape forzoso de 5h, aceptado.
    solape = max(
        0, min(v.mejor.fin, v.peor.fin) - max(v.mejor.inicio, v.peor.inicio)
    )
    assert solape == 5


# ---------- Tests ADR-010: activación de actividades por temporada ----------

def _df_benigno(fecha: date) -> "pd.DataFrame":
    """DataFrame con valores benignos (no dispara reglas) para test."""
    return _hourly_df(
        fecha,
        {
            "temperature_2m": [10.0] * 24,
            "windspeed_10m": [10.0] * 24,
            "windgusts_10m": [20.0] * 24,
            "cloudcover": [30.0] * 24,
            "precipitation": [0.0] * 24,
            "relative_humidity_2m": [50.0] * 24,
            "cape": [100.0] * 24,
            "weathercode": [1] * 24,
        },
    )


def test_actividad_no_activa_devuelve_none(actividades, zona_benasque):
    """Skimo en julio (no en meses_activos 11-5) → evaluar_dia devuelve None."""
    fecha = date(2026, 7, 15)
    df = _df_benigno(fecha)
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)
    assert ev is None


def test_actividad_activa_evalua_normalmente(actividades, zona_benasque):
    """Skimo en febrero (en meses_activos) → evaluar_dia devuelve EvaluacionDia."""
    fecha = date(2026, 2, 15)
    df = _df_benigno(fecha)
    df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
    prev = _prevision(zona_benasque, df_enr)

    skimo = _actividad(actividades, "skimo")
    ev = evaluar_dia(prev, skimo, fecha)
    assert ev is not None
    assert ev.semaforo in {"VERDE", "AMBAR", "ROJO", "SIN_DATOS"}


def test_actividad_sin_meses_activos_se_evalua_siempre(zona_benasque):
    """Actividad sin campo meses_activos (compat) → se evalúa en cualquier mes."""
    actividad_custom = {
        "id": "custom",
        "nombre": "Custom (sin meses_activos)",
        "franja_horaria": [7, 17],
        "ventana_minima_h": 3,
        "requiere_aviso_aludes": False,
        # SIN meses_activos
        "reglas": [
            {
                "variable": "windspeed_10m",
                "agg": "mean",
                "op": ">",
                "rojo": 100,
                "unidad": "km/h",
                "descripcion": "Viento medio",
            },
        ],
    }
    for mes in [1, 6, 9, 12]:
        fecha = date(2026, mes, 15)
        df = _df_benigno(fecha)
        df_enr = enriquecer_con_derivadas(df, elevacion_zona_m=2200)
        prev = _prevision(zona_benasque, df_enr)
        ev = evaluar_dia(prev, actividad_custom, fecha)
        assert ev is not None, f"sin meses_activos debería evaluarse en mes {mes}"


def test_transicion_mes_30_jun_1_jul_alpinismo_invierno(
    actividades, zona_benasque
):
    """alpinismo_invierno activo 30-jun (mes 6), no activo 1-jul (mes 7)."""
    alp_inv = _actividad(actividades, "alpinismo_invierno")

    f_30jun = date(2026, 6, 30)
    df_30jun = _df_benigno(f_30jun)
    df_30jun = enriquecer_con_derivadas(df_30jun, elevacion_zona_m=2200)
    prev_30jun = _prevision(zona_benasque, df_30jun)
    ev_30jun = evaluar_dia(prev_30jun, alp_inv, f_30jun)
    assert ev_30jun is not None, "junio en meses_activos de alpinismo_invierno"

    f_1jul = date(2026, 7, 1)
    df_1jul = _df_benigno(f_1jul)
    df_1jul = enriquecer_con_derivadas(df_1jul, elevacion_zona_m=2200)
    prev_1jul = _prevision(zona_benasque, df_1jul)
    ev_1jul = evaluar_dia(prev_1jul, alp_inv, f_1jul)
    assert ev_1jul is None, "julio NO en meses_activos de alpinismo_invierno"


def test_transicion_mes_31_may_1_jun_skimo(actividades, zona_benasque):
    """skimo activo 31-may (mes 5), no activo 1-jun (mes 6)."""
    skimo = _actividad(actividades, "skimo")

    f_31may = date(2026, 5, 31)
    df_31may = _df_benigno(f_31may)
    df_31may = enriquecer_con_derivadas(df_31may, elevacion_zona_m=2200)
    prev_31may = _prevision(zona_benasque, df_31may)
    ev_31may = evaluar_dia(prev_31may, skimo, f_31may)
    assert ev_31may is not None, "mayo en meses_activos de skimo"

    f_1jun = date(2026, 6, 1)
    df_1jun = _df_benigno(f_1jun)
    df_1jun = enriquecer_con_derivadas(df_1jun, elevacion_zona_m=2200)
    prev_1jun = _prevision(zona_benasque, df_1jun)
    ev_1jun = evaluar_dia(prev_1jun, skimo, f_1jun)
    assert ev_1jun is None, "junio NO en meses_activos de skimo"
