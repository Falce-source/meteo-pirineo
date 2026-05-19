"""Cliente Open-Meteo para meteo-pirineo.

Lee zonas desde ``config/zonas.yaml`` y obtiene la previsión horaria
para cada zona contra la API pública de Open-Meteo (sin clave).

Uso CLI:
    python -m src.fetch

Uso programático:
    from src.fetch import cargar_zonas, fetch_zona
    zonas = cargar_zonas()
    prev = fetch_zona(zonas[0])
    prev.horario  # DataFrame
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import requests_cache
import yaml

# Endpoint público (sin clave).
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Variables horarias solicitadas. El orden importa: Open-Meteo respeta
# este orden al construir las columnas en la respuesta.
# `freezing_level_height` se incluye aunque ARPEGE no la sirva: se rellena
# localmente en src/derivadas.py (ver ADR-004).
HOURLY_VARIABLES: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "weathercode",
    "snowfall",
    "cloudcover",
    "windspeed_10m",
    "windgusts_10m",
    "winddirection_10m",
    "cape",
    "freezing_level_height",
]

TIMEZONE = "Europe/Madrid"
# Modelo por defecto v0.1 (ver docs/decisiones.md, ADR-004 que supera a
# ADR-001). ARPEGE Europa (~25 km) cubre 111 h, suficiente para los 5
# días previstos. Su menor resolución frente a AROME implica vientos en
# cresta posiblemente subestimados; recalibrar umbrales tras uso real.
MODELO_DEFAULT = "meteofrance_arpege_europe"
TIMEOUT_S = 30
CACHE_PATH = ".cache/openmeteo"
CACHE_EXPIRE_S = 24 * 3600  # 24h

logger = logging.getLogger("src.fetch")


@dataclass
class PrevisionMeteo:
    """Resultado de un fetch contra Open-Meteo para una zona."""

    zona: dict[str, Any]
    timestamp_fetch: datetime
    horario: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


def cargar_zonas(path: str | Path = "config/zonas.yaml") -> list[dict[str, Any]]:
    """Lee el YAML de zonas y devuelve la lista de zonas.

    Args:
        path: Ruta al fichero YAML. Por defecto ``config/zonas.yaml``
            relativo al CWD.

    Returns:
        Lista de zonas (dicts) con las claves declaradas en el YAML.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    zonas = data.get("zonas", [])
    if not isinstance(zonas, list):
        raise ValueError(f"'zonas' en {path} debe ser una lista")
    return zonas


def _build_session() -> requests.Session:
    """Construye una sesión HTTP con caché SQLite de 24h."""
    Path(".cache").mkdir(exist_ok=True)
    session = requests_cache.CachedSession(
        cache_name=CACHE_PATH,
        backend="sqlite",
        expire_after=CACHE_EXPIRE_S,
        allowable_methods=("GET",),
    )
    return session


def _build_params(
    zona: dict[str, Any], forecast_days: int, modelo: str
) -> dict[str, Any]:
    """Construye los query params para la llamada a Open-Meteo."""
    try:
        lat = zona["latitud"]
        lon = zona["longitud"]
        elev = zona["elevacion_m"]
    except KeyError as e:
        raise KeyError(f"Zona sin clave requerida: {e}") from e

    return {
        "latitude": lat,
        "longitude": lon,
        "elevation": elev,
        "hourly": ",".join(HOURLY_VARIABLES),
        "models": modelo,
        "forecast_days": forecast_days,
        "timezone": TIMEZONE,
        "windspeed_unit": "kmh",
    }


def _parse_response(
    payload: dict[str, Any], modelo: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convierte la respuesta JSON de Open-Meteo en DataFrame + metadata.

    El DataFrame queda indexado por ``time`` como ``DatetimeIndex`` con
    timezone ``Europe/Madrid``. Las columnas son las variables solicitadas;
    si alguna no viene en la respuesta, se crea con NaN y se loguea warning.
    """
    hourly = payload.get("hourly", {}) or {}
    times = hourly.get("time")
    if not times:
        raise ValueError("Respuesta sin 'hourly.time'")

    idx = pd.to_datetime(times)
    # Open-Meteo entrega tiempos naive en la timezone solicitada.
    if idx.tz is None:
        idx = idx.tz_localize(TIMEZONE, nonexistent="shift_forward", ambiguous="NaT")
    else:
        idx = idx.tz_convert(TIMEZONE)
    idx.name = "time"

    columnas: dict[str, list[Any]] = {}
    for var in HOURLY_VARIABLES:
        if var in hourly and hourly[var] is not None:
            columnas[var] = hourly[var]
        else:
            logger.warning(
                "Variable '%s' no presente en la respuesta; columna con NaN", var
            )
            columnas[var] = [float("nan")] * len(idx)

    df = pd.DataFrame(columnas, index=idx)

    # Tipado numérico (Open-Meteo entrega números, pero garantizamos
    # el cast por si llega null/None puntual).
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    metadata: dict[str, Any] = {
        "modelo_solicitado": modelo,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "elevation": payload.get("elevation"),
        "timezone": payload.get("timezone"),
        "timezone_abbreviation": payload.get("timezone_abbreviation"),
        "utc_offset_seconds": payload.get("utc_offset_seconds"),
        "generationtime_ms": payload.get("generationtime_ms"),
        "hourly_units": payload.get("hourly_units", {}),
    }

    return df, metadata


def fetch_zona(
    zona: dict[str, Any],
    forecast_days: int = 5,
    modelo: str = MODELO_DEFAULT,
    session: requests.Session | None = None,
) -> PrevisionMeteo:
    """Consulta Open-Meteo para una zona y devuelve la previsión.

    Args:
        zona: Diccionario tal como viene de ``zonas.yaml``. Debe
            contener al menos ``latitud``, ``longitud`` y
            ``elevacion_m``.
        forecast_days: Días de previsión (1-16). Por defecto 5.
        modelo: Identificador de modelo Open-Meteo. Por defecto
            ``meteofrance_arome_france`` (ver ADR-001).
        session: Sesión HTTP opcional. Si no se pasa, se crea una
            con caché SQLite de 24h en ``.cache/``.

    Returns:
        PrevisionMeteo con DataFrame horario y metadata.

    Raises:
        requests.RequestException: si la llamada falla.
        ValueError: si la respuesta no contiene horarios.
    """
    sess = session or _build_session()
    params = _build_params(zona, forecast_days, modelo)

    logger.info(
        "Fetch Open-Meteo zona=%s modelo=%s lat=%s lon=%s elev=%s days=%s",
        zona.get("id"),
        modelo,
        params["latitude"],
        params["longitude"],
        params["elevation"],
        forecast_days,
    )

    try:
        resp = sess.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT_S)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Error consultando Open-Meteo zona=%s: %s", zona.get("id"), e)
        raise

    payload = resp.json()
    df, metadata = _parse_response(payload, modelo)

    # Si Open-Meteo reporta una elevación distinta a la pedida (modelo
    # con su propio MDT), lo guardamos para visibilidad humana. No es
    # un error.
    metadata["elevacion_solicitada_m"] = zona.get("elevacion_m")
    elev_reportada = metadata.get("elevation")
    if elev_reportada is not None and zona.get("elevacion_m") is not None:
        diff = abs(float(elev_reportada) - float(zona["elevacion_m"]))
        if diff > 50:
            logger.info(
                "Elevación reportada por modelo (%s m) difiere de la solicitada "
                "(%s m) en zona=%s",
                elev_reportada,
                zona["elevacion_m"],
                zona.get("id"),
            )

    return PrevisionMeteo(
        zona=zona,
        timestamp_fetch=datetime.now(),
        horario=df,
        metadata=metadata,
    )


def _resumen_consola(prev: PrevisionMeteo) -> dict[str, Any]:
    """Genera un dict con métricas de sanity check para el primer día."""
    df = prev.horario
    if df.empty:
        return {}

    primer_dia = df.index[0].date()
    mask_primer_dia = df.index.date == primer_dia
    sub = df.loc[mask_primer_dia]

    return {
        "zona": prev.zona.get("id"),
        "fecha": str(primer_dia),
        "temp_min_C": round(float(sub["temperature_2m"].min()), 1),
        "temp_max_C": round(float(sub["temperature_2m"].max()), 1),
        "viento_medio_kmh": round(float(sub["windspeed_10m"].mean()), 1),
        "precip_total_mm": round(float(sub["precipitation"].sum()), 1),
    }


def main() -> None:
    """Entry-point CLI: fetch de todas las zonas + tabla resumen."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    zonas = cargar_zonas()
    filas: list[dict[str, Any]] = []
    for zona in zonas:
        prev = fetch_zona(zona)
        filas.append(_resumen_consola(prev))

    if filas:
        resumen = pd.DataFrame(filas)
        print()
        print("Resumen primer día por zona (sanity check):")
        print(resumen.to_string(index=False))
        print()


if __name__ == "__main__":
    main()
