"""Tests del cliente Open-Meteo.

Las respuestas HTTP se mockean con ``responses`` a partir del fixture
``tests/fixtures/openmeteo_response_sample.json``, capturado en vivo
durante el bootstrap de la semana 1.

No se hacen llamadas a red en estos tests.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import requests
import responses

from src.fetch import (
    HOURLY_VARIABLES,
    OPEN_METEO_URL,
    cargar_zonas,
    fetch_zona,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "openmeteo_response_sample.json"


@pytest.fixture(scope="module")
def fixture_payload() -> dict:
    """Carga el fixture JSON capturado en vivo."""
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def zona_benasque() -> dict:
    """Zona de prueba (coincide con la del fixture)."""
    return {
        "id": "benasque",
        "nombre": "Valle de Benasque (Cerler / bajo Aneto)",
        "macizo": "Pirineo aragonés",
        "latitud": 42.65,
        "longitud": 0.55,
        "elevacion_m": 2200,
    }


@pytest.fixture
def fresh_session() -> requests.Session:
    """Sesión plana sin caché para que ``responses`` pueda interceptar."""
    return requests.Session()


@responses.activate
def test_url_construction(zona_benasque, fixture_payload, fresh_session):
    """Verifica que se llama con todos los parámetros esperados."""
    responses.add(
        responses.GET,
        OPEN_METEO_URL,
        json=fixture_payload,
        status=200,
    )

    fetch_zona(zona_benasque, forecast_days=5, session=fresh_session)

    assert len(responses.calls) == 1
    called_url = responses.calls[0].request.url
    parsed = urlparse(called_url)
    qs = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == OPEN_METEO_URL
    assert qs["latitude"] == ["42.65"]
    assert qs["longitude"] == ["0.55"]
    assert qs["elevation"] == ["2200"]
    assert qs["models"] == ["meteofrance_arpege_europe"]
    assert qs["forecast_days"] == ["5"]
    assert qs["timezone"] == ["Europe/Madrid"]
    assert qs["windspeed_unit"] == ["kmh"]

    hourly_pedidas = qs["hourly"][0].split(",")
    assert hourly_pedidas == HOURLY_VARIABLES
    # precipitation_probability se retiró del set en Semana 2.5 (ADR-005).
    assert "precipitation_probability" not in hourly_pedidas


@responses.activate
def test_parseo_respuesta_valida(zona_benasque, fixture_payload, fresh_session):
    """Mockea la respuesta y verifica forma del DataFrame."""
    responses.add(
        responses.GET,
        OPEN_METEO_URL,
        json=fixture_payload,
        status=200,
    )

    prev = fetch_zona(zona_benasque, session=fresh_session)
    df = prev.horario

    # Index temporal tz-aware en Europe/Madrid.
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None
    assert str(df.index.tz) == "Europe/Madrid"
    assert df.index.name == "time"

    # ~120 filas (5 días * 24 h).
    assert 115 <= len(df) <= 125

    # 11 columnas (Semana 2.5: se retiró precipitation_probability).
    assert set(df.columns) == set(HOURLY_VARIABLES)
    assert len(df.columns) == 11

    # Tipos numéricos.
    for col in df.columns:
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} no es numérica"

    # Metadata enriquecida con elevación solicitada.
    assert prev.metadata["elevacion_solicitada_m"] == 2200
    assert prev.metadata["timezone"] == "Europe/Madrid"


@responses.activate
def test_variable_faltante_no_rompe(
    zona_benasque, fixture_payload, fresh_session, caplog
):
    """Si falta una variable (ej. 'cape'), columna con NaN + warning."""
    payload_sin_cape = json.loads(json.dumps(fixture_payload))
    payload_sin_cape["hourly"].pop("cape", None)

    responses.add(
        responses.GET,
        OPEN_METEO_URL,
        json=payload_sin_cape,
        status=200,
    )

    with caplog.at_level(logging.WARNING, logger="src.fetch"):
        prev = fetch_zona(zona_benasque, session=fresh_session)

    df = prev.horario
    assert "cape" in df.columns
    assert df["cape"].isna().all()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("cape" in r.getMessage() for r in warnings), (
        "Se esperaba warning mencionando 'cape'"
    )


def test_carga_zonas_yaml():
    """``cargar_zonas`` devuelve 2 zonas con las claves esperadas."""
    repo_root = Path(__file__).parent.parent
    zonas = cargar_zonas(repo_root / "config" / "zonas.yaml")

    assert len(zonas) == 2
    ids = {z["id"] for z in zonas}
    assert ids == {"benasque", "aran"}

    claves_obligatorias = {
        "id",
        "nombre",
        "macizo",
        "latitud",
        "longitud",
        "elevacion_m",
        "boletin_aludes",
    }
    for z in zonas:
        assert claves_obligatorias.issubset(z.keys()), (
            f"Faltan claves en zona {z.get('id')}: "
            f"{claves_obligatorias - z.keys()}"
        )
        assert isinstance(z["latitud"], (int, float))
        assert isinstance(z["longitud"], (int, float))
        assert isinstance(z["elevacion_m"], (int, float))
        assert "nombre" in z["boletin_aludes"]
        assert "url" in z["boletin_aludes"]
