"""Tests del orquestador ``src.main``.

Mockean ``fetch_zona`` para evitar tráfico de red y verifican el
comportamiento frente a fallos parciales.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import requests
from bs4 import BeautifulSoup

from src.fetch import HOURLY_VARIABLES, PrevisionMeteo
from src.main import main


def _df_benigno() -> pd.DataFrame:
    """DataFrame de 5 días (120 h) con valores que no disparan reglas."""
    idx = pd.date_range(
        "2026-05-19 00:00", periods=120, freq="h", tz="Europe/Madrid"
    )
    idx.name = "time"
    base: dict[str, list] = {
        "temperature_2m": [15.0] * 120,
        "relative_humidity_2m": [50.0] * 120,
        "precipitation": [0.0] * 120,
        "weathercode": [0] * 120,
        "snowfall": [0.0] * 120,
        "cloudcover": [20.0] * 120,
        "windspeed_10m": [10.0] * 120,
        "windgusts_10m": [20.0] * 120,
        "winddirection_10m": [180.0] * 120,
        "cape": [200.0] * 120,
        "freezing_level_height": [float("nan")] * 120,
    }
    # Asegurar que existen todas las columnas del set v0.1.
    for var in HOURLY_VARIABLES:
        base.setdefault(var, [float("nan")] * 120)
    return pd.DataFrame(base, index=idx)


def _fake_prevision_benigna(zona: dict) -> PrevisionMeteo:
    return PrevisionMeteo(
        zona=zona,
        timestamp_fetch=datetime(2026, 5, 19, 12, 0),
        horario=_df_benigno(),
        metadata={"modelo_solicitado": "test"},
    )


def test_main_continua_si_una_zona_falla(tmp_path):
    """Si Aran falla pero Benasque no, el HTML se genera con ambas zonas:
    Aran en SIN_DATOS con aviso de error, Benasque normal."""

    def fake_fetch_zona(zona, modelo=None, session=None, **kwargs):
        if zona["id"] == "aran":
            raise requests.ConnectionError("simulated connection error")
        return _fake_prevision_benigna(zona)

    with patch("src.main.fetch_zona", side_effect=fake_fetch_zona):
        main(modo="html", output_dir=str(tmp_path))

    html_path = Path(tmp_path) / "index.html"
    assert html_path.exists()
    contenido = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(contenido, "html.parser")

    # Aran: todas las celdas en SIN_DATOS, con aviso de error.
    aran_section = soup.find("section", id="zona-aran")
    assert aran_section is not None
    aran_cells = aran_section.find_all("button", class_="celda")
    assert len(aran_cells) == 25  # 5 actividades × 5 días
    for cell in aran_cells:
        assert "sin-datos" in cell.get("class", []), (
            f"celda aran no es SIN_DATOS: {cell.get('class')}"
        )
    # Aviso textual con la cadena de error.
    avisos_raw = aran_cells[0].get("data-avisos", "[]")
    assert "Error al obtener pronóstico" in avisos_raw, avisos_raw

    # Benasque: al menos una celda NO es sin-datos.
    benasque_section = soup.find("section", id="zona-benasque")
    assert benasque_section is not None
    benasque_cells = benasque_section.find_all("button", class_="celda")
    no_sd = [c for c in benasque_cells if "sin-datos" not in c.get("class", [])]
    assert len(no_sd) > 0, "Benasque debería tener celdas evaluadas"


def test_main_aborta_si_todas_las_zonas_fallan(tmp_path):
    """Si TODAS las zonas fallan, main sale con SystemExit no-cero."""

    def fake_fetch_zona(zona, modelo=None, session=None, **kwargs):
        raise requests.ConnectionError("simulated total outage")

    html_path = Path(tmp_path) / "index.html"
    with patch("src.main.fetch_zona", side_effect=fake_fetch_zona):
        with pytest.raises(SystemExit) as exc_info:
            main(modo="html", output_dir=str(tmp_path))

    assert exc_info.value.code != 0
    # No se debe haber generado HTML (se preserva el último despliegue
    # válido en producción).
    assert not html_path.exists()
