"""Tests de ``src.render``.

Generan un HTML sintético y lo inspeccionan con BeautifulSoup.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.evaluar import EvaluacionDia, MotivoSemaforo, Ventana, VentanasDia
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


# ---------- Tests Semana 5: ventanas óptimas en modal (ADR-007) ----------

@pytest.fixture
def paquetes_con_ventanas() -> dict:
    """Estructura con tres tipos de evaluación: día homogéneo,
    oportunidad (semáforo global AMBAR pero mejor ventana VERDE),
    y una actividad sin ventana_minima_h declarada."""
    zona = ZONAS_FAKE[0]
    fecha = FECHAS_FAKE[0]

    # 1) Celda HOMOGÉNEA (ADR-009): skimo, una sola ventana en `homogenea`.
    ev_homogenea = _eval(zona["id"], "skimo", fecha, "VERDE")
    ev_homogenea.ventanas = VentanasDia(
        homogenea=Ventana(inicio=7, fin=11, semaforo="VERDE"),
        duracion_h=4,
    )

    # 2) Celda OPORTUNIDAD: alpinismo_invierno, semáforo global AMBAR
    #    pero hay ventana VERDE matinal.
    ev_oportunidad = _eval(
        zona["id"], "alpinismo_invierno", fecha, "AMBAR",
        motivos=[
            MotivoSemaforo(
                descripcion="Nubosidad media en cota",
                variable="cloudcover",
                valor_observado=75.0,
                umbral_disparado=70.0,
                nivel="AMBAR",
                unidad="%",
                op=">",
            )
        ],
    )
    ev_oportunidad.ventanas = VentanasDia(
        mejor=Ventana(inicio=7, fin=13, semaforo="VERDE"),
        peor=Ventana(inicio=12, fin=18, semaforo="AMBAR"),
        duracion_h=6,
    )

    # 3) Celda SIN VENTANAS: actividad fake sin ventana_minima_h.
    ev_sin = _eval(zona["id"], "trail", fecha, "VERDE")
    ev_sin.ventanas = None  # explícito: actividad no declara ventana_minima_h

    # Rellenamos el resto con celdas vacías (verde sin ventanas).
    evs = []
    map_celdas = {
        ("skimo", fecha): ev_homogenea,
        ("alpinismo_invierno", fecha): ev_oportunidad,
        ("trail", fecha): ev_sin,
    }
    for f in FECHAS_FAKE:
        for act in ACTIVIDADES_FAKE:
            ev = map_celdas.get((act["id"], f))
            if ev is None:
                ev = _eval(zona["id"], act["id"], f, "VERDE")
            evs.append(ev)
    return {zona["id"]: {"zona": zona, "evaluaciones": evs}}


def test_html_modal_muestra_ventanas(tmp_path, paquetes_con_ventanas):
    """Una celda heterogénea (ADR-009) serializa mejor + peor en
    data-ventanas, sin campo homogenea; el JS contiene la plantilla."""
    contenido, _ = _render_to(tmp_path, paquetes_con_ventanas)
    soup = BeautifulSoup(contenido, "html.parser")

    # data-ventanas en la celda de oportunidad (heterogénea).
    celda = soup.find(id="benasque-alpinismo_invierno-2026-05-19")
    raw = celda.get("data-ventanas")
    assert raw and raw != "null"
    ventanas = json.loads(raw)
    assert ventanas["duracion_h"] == 6
    assert "homogenea" not in ventanas  # caso heterogéneo
    assert ventanas["mejor"]["inicio"] == 7
    assert ventanas["mejor"]["fin"] == 13
    assert ventanas["mejor"]["semaforo"] == "VERDE"
    assert ventanas["peor"]["semaforo"] == "AMBAR"

    # Plantilla JS contiene "Mejor ventana" y formato HH:00.
    assert "Mejor ventana" in contenido
    assert "Peor ventana" in contenido
    # El helper fmtHora produce "HH:00" con padStart.
    assert "padStart(2, '0')" in contenido


def test_html_modal_omite_ventanas_si_actividad_no_las_declara(
    tmp_path, paquetes_con_ventanas
):
    """Una celda cuya evaluación tiene ventanas=None lleva
    data-ventanas="null"; el JS no renderiza la sección."""
    contenido, _ = _render_to(tmp_path, paquetes_con_ventanas)
    soup = BeautifulSoup(contenido, "html.parser")

    celda = soup.find(id="benasque-trail-2026-05-19")
    raw = celda.get("data-ventanas")
    assert raw == "null", f"esperaba null, salió {raw!r}"

    # Condición JS: la sección se omite si no hay homogenea ni mejor+peor.
    assert "ventanas.homogenea || (ventanas.mejor && ventanas.peor)" in contenido


def test_html_modal_dia_homogeneo(tmp_path, paquetes_con_ventanas):
    """ADR-009: el caso homogéneo se serializa con campo `homogenea`
    poblado; el JS muestra 'Todo el día homogéneo'."""
    contenido, _ = _render_to(tmp_path, paquetes_con_ventanas)
    soup = BeautifulSoup(contenido, "html.parser")

    celda = soup.find(id="benasque-skimo-2026-05-19")
    raw = celda.get("data-ventanas")
    ventanas = json.loads(raw)

    # Caso homogéneo: solo `homogenea`, sin mejor/peor.
    assert "homogenea" in ventanas
    assert ventanas["homogenea"]["semaforo"] == "VERDE"
    assert "mejor" not in ventanas
    assert "peor" not in ventanas

    # Plantilla JS contiene el texto "Todo el día homogéneo".
    assert "Todo el día homogéneo" in contenido


# ---------- Tests ADR-010: activación por temporada en render ----------

def _render_to_with_horizon(
    tmp_path: Path, paquetes: dict, fechas_horizonte: list[date]
) -> tuple[str, Path]:
    """Variante de _render_to que inyecta fechas_horizonte por zona."""
    out = tmp_path / "index.html"
    # Cada paquete recibe explícitamente las fechas del horizonte.
    paquetes_con_horizon = {
        zid: {**p, "fechas_horizonte": list(fechas_horizonte)}
        for zid, p in paquetes.items()
    }
    path = renderizar_html(
        evaluaciones_por_zona=paquetes_con_horizon,
        timestamp=datetime(2026, 6, 30, 12, 0),
        modelo="meteofrance_arpege_europe",
        actividades=ACTIVIDADES_FAKE,
        output_path=out,
    )
    return path.read_text(encoding="utf-8"), path


def test_fila_actividad_omitida_si_ningun_dia_activo(tmp_path):
    """Si en TODO el horizonte la actividad no tiene evaluación,
    su fila NO aparece en el HTML (ADR-010)."""
    zona = ZONAS_FAKE[0]
    # Horizonte de 3 días en julio: skimo no tiene ninguna evaluación.
    fechas_horizonte = [date(2026, 7, i) for i in (1, 2, 3)]
    # Solo evaluaciones de alpinismo_estival (activo en julio).
    evs = [
        _eval(zona["id"], "alpinismo_estival", f, "VERDE")
        for f in fechas_horizonte
    ]
    paquetes = {zona["id"]: {"zona": zona, "evaluaciones": evs}}

    contenido, _ = _render_to_with_horizon(tmp_path, paquetes, fechas_horizonte)
    soup = BeautifulSoup(contenido, "html.parser")

    # Filas presentes (th scope=row).
    nombres_fila = [th.get_text() for th in soup.find_all("th", attrs={"scope": "row"})]
    assert "Esquí de montaña" not in nombres_fila
    assert "Alpinismo invernal" not in nombres_fila
    assert "Trail running" not in nombres_fila
    assert "Ciclismo" not in nombres_fila
    # La única fila visible es alpinismo_estival.
    assert "Alpinismo estival" in nombres_fila


def test_celda_fuera_temporada_se_muestra_si_otros_dias_activos(tmp_path):
    """Horizonte cruza el cambio de mes: la actividad está activa unos
    días y no otros. Los días no activos aparecen como celdas
    fuera-temporada (gris)."""
    zona = ZONAS_FAKE[0]
    # Horizonte 30-jun a 4-jul (cruza el corte mensual).
    fechas_horizonte = [date(2026, 6, 30)] + [date(2026, 7, d) for d in (1, 2, 3, 4)]
    # alpinismo_invierno activo solo el 30-jun (junio en su lista 11-6).
    evs = [_eval(zona["id"], "alpinismo_invierno", date(2026, 6, 30), "VERDE")]
    # alpinismo_estival activo todos los días (junio y julio en 6-10).
    evs.extend(
        _eval(zona["id"], "alpinismo_estival", f, "VERDE")
        for f in fechas_horizonte
    )
    paquetes = {zona["id"]: {"zona": zona, "evaluaciones": evs}}

    contenido, _ = _render_to_with_horizon(tmp_path, paquetes, fechas_horizonte)
    soup = BeautifulSoup(contenido, "html.parser")

    # 4 celdas fuera-temporada (alpinismo_invierno en julio: 1, 2, 3, 4).
    celdas_ft = soup.find_all(class_="fuera-temporada")
    assert len(celdas_ft) == 4

    # 30-jun: celda normal (button) para alpinismo_invierno.
    celda_30jun = soup.find(id="benasque-alpinismo_invierno-2026-06-30")
    assert celda_30jun is not None
    assert celda_30jun.name == "button"
    assert "verde" in celda_30jun.get("class", [])


def test_celda_fuera_temporada_no_es_clickable(tmp_path):
    """Las celdas fuera-temporada NO son <button>, NO llevan atributos
    data-* y por tanto el JS de modal no las abre."""
    zona = ZONAS_FAKE[0]
    fechas_horizonte = [date(2026, 6, 30)] + [date(2026, 7, d) for d in (1, 2, 3, 4)]
    evs = [_eval(zona["id"], "alpinismo_invierno", date(2026, 6, 30), "VERDE")]
    evs.extend(
        _eval(zona["id"], "alpinismo_estival", f, "VERDE")
        for f in fechas_horizonte
    )
    paquetes = {zona["id"]: {"zona": zona, "evaluaciones": evs}}

    contenido, _ = _render_to_with_horizon(tmp_path, paquetes, fechas_horizonte)
    soup = BeautifulSoup(contenido, "html.parser")

    for ft in soup.find_all(class_="fuera-temporada"):
        # No es un <button>.
        assert ft.name != "button"
        # No tiene NINGÚN atributo data-*.
        for attr in ft.attrs:
            assert not attr.startswith("data-"), (
                f"celda fuera-temporada con atributo data-* prohibido: {attr}"
            )
        # Lleva el tooltip 'Fuera de temporada'.
        assert ft.get("title") == "Fuera de temporada"
