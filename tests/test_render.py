"""Tests de ``src.render``.

Generan un HTML sintético y lo inspeccionan con BeautifulSoup.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.evaluar import EvaluacionDia, MotivoSemaforo
from src.render import renderizar_html


# ---------- Fixtures ----------

ZONAS_FAKE: list[dict] = [
    {
        "id": "benasque",
        "nombre": "Valle de Benasque",
        "macizo": "Pirineo aragonés",
        "latitud": 42.65,
        "longitud": 0.55,
        "elevacion_m": 2200,
        "boletin_aludes": {
            "nombre": "AEMET - Pirineo aragonés",
            "url": "https://www.aemet.es/montana?w=ag0",
        },
    },
    {
        "id": "aran",
        "nombre": "Vall d'Aran",
        "macizo": "Pirineo catalán",
        "latitud": 42.70,
        "longitud": 0.93,
        "elevacion_m": 2070,
        "boletin_aludes": {
            "nombre": "Lauegi (ICGC)",
            "url": "https://lauegi.report/",
        },
    },
]

ACTIVIDADES_FAKE: list[dict] = [
    {"id": "skimo", "nombre": "Esquí de montaña"},
    {"id": "alpinismo_invierno", "nombre": "Alpinismo invernal"},
    {"id": "alpinismo_estival", "nombre": "Alpinismo estival"},
    {"id": "trail", "nombre": "Trail running"},
    {"id": "ciclismo", "nombre": "Ciclismo"},
]

FECHAS_FAKE: list[date] = [date(2026, 5, 19 + i) for i in range(5)]


def _eval(
    zona_id: str,
    act_id: str,
    fecha: date,
    semaforo: str,
    motivos: list[MotivoSemaforo] | None = None,
    avisos: list[str] | None = None,
    datos_clave: dict[str, float] | None = None,
) -> EvaluacionDia:
    return EvaluacionDia(
        zona_id=zona_id,
        actividad_id=act_id,
        fecha=fecha,
        semaforo=semaforo,
        motivos=motivos or [],
        datos_clave=datos_clave or {},
        avisos=avisos or [],
    )


@pytest.fixture
def paquetes_basicos() -> dict:
    """2 zonas × 5 actividades × 5 días, todos VERDE excepto un ROJO."""
    paquetes: dict[str, dict] = {}
    for zona in ZONAS_FAKE:
        evs = []
        for f in FECHAS_FAKE:
            for act in ACTIVIDADES_FAKE:
                semaforo = "VERDE"
                motivos: list[MotivoSemaforo] = []
                # Una celda ROJA: skimo de Benasque el primer día.
                if (
                    zona["id"] == "benasque"
                    and act["id"] == "skimo"
                    and f == FECHAS_FAKE[0]
                ):
                    semaforo = "ROJO"
                    motivos = [
                        MotivoSemaforo(
                            descripcion="Ráfaga máxima",
                            variable="windgusts_10m",
                            valor_observado=78.0,
                            umbral_disparado=70.0,
                            nivel="ROJO",
                            unidad="km/h",
                            op=">",
                        )
                    ]
                # Una celda AMBAR: alpinismo_estival Aran segundo día.
                if (
                    zona["id"] == "aran"
                    and act["id"] == "alpinismo_estival"
                    and f == FECHAS_FAKE[1]
                ):
                    semaforo = "AMBAR"
                # Una celda SIN_DATOS: ciclismo Aran último día.
                if (
                    zona["id"] == "aran"
                    and act["id"] == "ciclismo"
                    and f == FECHAS_FAKE[4]
                ):
                    semaforo = "SIN_DATOS"

                evs.append(
                    _eval(zona["id"], act["id"], f, semaforo, motivos)
                )
        paquetes[zona["id"]] = {"zona": zona, "evaluaciones": evs}
    return paquetes


def _render_to(tmp_path: Path, paquetes: dict) -> tuple[str, Path]:
    out = tmp_path / "index.html"
    path = renderizar_html(
        evaluaciones_por_zona=paquetes,
        timestamp=datetime(2026, 5, 19, 14, 32),
        modelo="meteofrance_arpege_europe",
        actividades=ACTIVIDADES_FAKE,
        output_path=out,
    )
    return path.read_text(encoding="utf-8"), path


# ---------- Tests ----------

def test_html_se_genera_y_es_valido(tmp_path, paquetes_basicos):
    contenido, path = _render_to(tmp_path, paquetes_basicos)
    assert path.exists()
    assert contenido.startswith("<!DOCTYPE html>")
    soup = BeautifulSoup(contenido, "html.parser")
    assert soup.html is not None
    assert soup.head is not None
    assert soup.body is not None
    assert soup.find("header", class_="principal") is not None
    assert soup.main is not None
    assert soup.find("footer", class_="principal") is not None


def test_html_contiene_todas_las_zonas(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")
    zonas_section = soup.find_all("section", class_="zona")
    assert len(zonas_section) == 2
    ids = {s.get("id") for s in zonas_section}
    assert ids == {"zona-benasque", "zona-aran"}


def test_html_contiene_todas_las_celdas(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")
    celdas = soup.find_all("button", class_="celda")
    assert len(celdas) == 2 * 5 * 5  # 50


def test_html_clase_color_correcta(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")

    # ROJO: skimo Benasque 19-may.
    rojo = soup.find(id="benasque-skimo-2026-05-19")
    assert rojo is not None
    assert "rojo" in rojo.get("class", [])

    # AMBAR: alpinismo_estival Aran 20-may.
    ambar = soup.find(id="aran-alpinismo_estival-2026-05-20")
    assert ambar is not None
    assert "ambar" in ambar.get("class", [])

    # SIN_DATOS: ciclismo Aran 23-may.
    sd = soup.find(id="aran-ciclismo-2026-05-23")
    assert sd is not None
    assert "sin-datos" in sd.get("class", [])

    # VERDE: cualquier celda no contemplada arriba.
    verde = soup.find(id="benasque-trail-2026-05-20")
    assert verde is not None
    assert "verde" in verde.get("class", [])


def test_html_aviso_aludes_presente(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")
    aviso = soup.find(class_="aviso-aludes")
    assert aviso is not None
    enlaces = [a["href"] for a in aviso.find_all("a", href=True)]
    assert any("lauegi" in h.lower() for h in enlaces)
    assert any("aemet" in h.lower() for h in enlaces)


def test_html_motivos_serializados_como_data_attr(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")
    rojo = soup.find(id="benasque-skimo-2026-05-19")
    raw = rojo.get("data-motivos")
    assert raw, "data-motivos vacío en celda ROJA"
    motivos = json.loads(raw)
    assert isinstance(motivos, list)
    assert len(motivos) == 1
    m = motivos[0]
    assert m["nivel"] == "ROJO"
    assert m["variable"] == "windgusts_10m"
    assert m["umbral_disparado"] == 70.0
    assert m["op"] == ">"


def test_html_responsive_meta_viewport(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")
    meta = soup.find("meta", attrs={"name": "viewport"})
    assert meta is not None
    content = meta.get("content", "")
    assert "width=device-width" in content
    assert "initial-scale=1" in content


def test_html_no_referencia_recursos_externos(tmp_path, paquetes_basicos):
    contenido, _ = _render_to(tmp_path, paquetes_basicos)
    soup = BeautifulSoup(contenido, "html.parser")

    # Sin <link rel=stylesheet href=http(s):...>
    for link in soup.find_all("link"):
        href = link.get("href", "")
        rel = link.get("rel", []) or []
        if "stylesheet" in rel:
            assert not href.startswith(("http://", "https://", "//")), (
                f"stylesheet externo: {href}"
            )

    # Sin <script src=http(s):...>
    for script in soup.find_all("script"):
        src = script.get("src", "")
        if src:
            assert not src.startswith(("http://", "https://", "//")), (
                f"script externo: {src}"
            )
