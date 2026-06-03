"""Lógica pura de evaluación de actividades en función de la previsión.

Sin I/O, sin red, sin escritura. Recibe ``PrevisionMeteo`` (de
``src.fetch``) y un dict de actividad (de ``config/actividades.yaml``)
y devuelve una ``EvaluacionDia``.

Reglas resumen:
- Cada actividad declara una lista de reglas. Cada regla = variable
  + agregación + operador + umbral(es) ámbar/rojo.
- El peor componente determina el semáforo del día: ROJO > AMBAR > VERDE.
- Reglas con ``op == "informativo"`` solo reportan, no afectan al color.
- Variables derivadas pendientes (snowfall_48h_previas) se saltan y se
  añade un aviso pendiente.
- Si la previsión no tiene datos para la fecha (más allá del horizonte
  del modelo), el semáforo es ``SIN_DATOS`` (ver ADR-003).
- Mejor/peor ventana del día se calculan como sub-evaluación con
  ventana deslizante (ADR-007).
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from src.fetch import PrevisionMeteo

# Variables declaradas en actividades.yaml que aún no se calculan.
# Cualquier regla que las referencie se salta y se añade un aviso.
#
# Semana 4: ``indice_tormenta`` dejó esta categoría — ahora se calcula
# en ``src.tormenta`` y se inyecta vía ``src.derivadas`` (ADR-006).
VARIABLES_DERIVADAS_PENDIENTES: set[str] = {
    "snowfall_48h_previas",
}

# Meses en los que se considera relevante el boletín de aludes (criterio
# simple v0.1). Cubre temporada de nieve potencialmente activa.
MESES_AVISO_ALUDES: set[int] = {11, 12, 1, 2, 3, 4, 5}

OPERADORES: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

AGREGACIONES: dict[str, Callable[[pd.Series], float]] = {
    "max": lambda s: s.max(),
    "min": lambda s: s.min(),
    "mean": lambda s: s.mean(),
    "sum": lambda s: s.sum(),
}

FRANJA_DEFAULT: tuple[int, int] = (7, 17)


@dataclass
class MotivoSemaforo:
    descripcion: str
    variable: str
    valor_observado: float | None
    umbral_disparado: float | None
    nivel: str  # "AMBAR" | "ROJO" | "INFORMATIVO"
    unidad: str | None
    # Operador comparativo de la regla: ">", ">=", "<", "<=" o
    # "informativo". Usado por el render para componer el texto del
    # umbral (p. ej. "umbral rojo: >50 km/h").
    op: str | None = None
    # True si el valor proviene de una variable derivada / estimada
    # localmente (p. ej. FLH por lapse rate). Render añade "[estimado]".
    estimada: bool = False


@dataclass
class Ventana:
    """Sub-evaluación de una franja arbitraria del día."""

    inicio: int                              # hora de inicio (0-23), inclusiva
    fin: int                                 # hora de fin (exclusiva)
    semaforo: str                            # VERDE | AMBAR | ROJO | SIN_DATOS
    motivos: list[MotivoSemaforo] = field(default_factory=list)
    datos_clave: dict[str, float] = field(default_factory=dict)


@dataclass
class VentanasDia:
    """Resumen de mejor/peor sub-ventana del día.

    Política de exposición (ADR-007, refinada por ADR-009):

    - Si ``homogenea`` está poblada → todas las sub-ventanas tienen el
      mismo semáforo y el render muestra una sola línea "Todo el día
      homogéneo".
    - Si ``mejor`` y ``peor`` están poblados → existe diferenciación
      semafórica y el render muestra ambas. El par concreto se elige
      minimizando el solape temporal entre ambas (ADR-009).
    - Si todos son ``None`` → la actividad no declaró ``ventana_minima_h``.
    """

    homogenea: Ventana | None = None
    mejor: Ventana | None = None
    peor: Ventana | None = None
    duracion_h: int = 0

    @property
    def es_homogenea(self) -> bool:
        return self.homogenea is not None


@dataclass
class EvaluacionDia:
    zona_id: str
    actividad_id: str
    fecha: date
    semaforo: str  # "VERDE" | "AMBAR" | "ROJO" | "SIN_DATOS"
    motivos: list[MotivoSemaforo] = field(default_factory=list)
    datos_clave: dict[str, float] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    # Mejor/peor sub-ventana del día (ADR-007). ``None`` si la actividad
    # no declara ``ventana_minima_h`` en su configuración.
    ventanas: VentanasDia | None = None


def cargar_actividades(
    path: str | Path = "config/actividades.yaml",
) -> list[dict[str, Any]]:
    """Lee el YAML de actividades y devuelve la lista de actividades."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    acts = data.get("actividades", [])
    if not isinstance(acts, list):
        raise ValueError(f"'actividades' en {path} debe ser una lista")
    return acts


def _filtrar_franja(
    df: pd.DataFrame, fecha: date, franja: tuple[int, int] | list[int]
) -> pd.DataFrame:
    """Filtra el DataFrame a la franja horaria del día indicado.

    La franja se interpreta como cerrada por ambos extremos:
    ``[inicio, fin]`` incluye tanto la hora ``inicio`` como ``fin``.
    """
    inicio, fin = franja[0], franja[1]
    idx = df.index
    mask = (
        (idx.date == fecha)
        & (idx.hour >= inicio)
        & (idx.hour <= fin)
    )
    return df.loc[mask]


def _evaluar_regla_simple(
    serie: pd.Series,
    regla: dict[str, Any],
) -> tuple[float | None, MotivoSemaforo | None]:
    """Evalúa una regla con agregación pandas estándar.

    Devuelve (valor_agregado, motivo_o_None).
    Si valor_agregado es None significa que no había datos.
    """
    agg_name = regla.get("agg")
    op_name = regla.get("op")
    umbral_rojo = regla.get("rojo")
    umbral_ambar = regla.get("ambar")
    unidad = regla.get("unidad")
    descripcion = regla.get("descripcion", regla["variable"])
    variable = regla["variable"]

    agg_fn = AGREGACIONES.get(agg_name)
    if agg_fn is None:
        return None, None

    valor = agg_fn(serie)
    if pd.isna(valor):
        return None, None
    valor_f = float(valor)

    # Caso informativo: siempre se reporta, nunca sube semáforo.
    if op_name == "informativo":
        return valor_f, MotivoSemaforo(
            descripcion=descripcion,
            variable=variable,
            valor_observado=valor_f,
            umbral_disparado=(
                float(umbral_ambar) if umbral_ambar is not None else None
            ),
            nivel="INFORMATIVO",
            unidad=unidad,
            op="informativo",
        )

    op_fn = OPERADORES.get(op_name)
    if op_fn is None:
        return valor_f, None

    if umbral_rojo is not None and op_fn(valor_f, umbral_rojo):
        return valor_f, MotivoSemaforo(
            descripcion=descripcion,
            variable=variable,
            valor_observado=valor_f,
            umbral_disparado=float(umbral_rojo),
            nivel="ROJO",
            unidad=unidad,
            op=op_name,
        )
    if umbral_ambar is not None and op_fn(valor_f, umbral_ambar):
        return valor_f, MotivoSemaforo(
            descripcion=descripcion,
            variable=variable,
            valor_observado=valor_f,
            umbral_disparado=float(umbral_ambar),
            nivel="AMBAR",
            unidad=unidad,
            op=op_name,
        )
    return valor_f, None


def _evaluar_regla_cualquier_franja(
    serie: pd.Series,
    regla: dict[str, Any],
) -> tuple[bool | None, MotivoSemaforo | None]:
    """Evalúa una regla con agg 'cualquier_franja'.

    Devuelve (True/False/None, motivo_o_None). El bool indica si la
    condición se cumplió en algún punto. None = no había datos.
    """
    op_name = regla.get("op")
    op_fn = OPERADORES.get(op_name)
    if op_fn is None:
        return None, None
    umbral_rojo = regla.get("rojo")
    umbral_ambar = regla.get("ambar")
    umbral = umbral_rojo if umbral_rojo is not None else umbral_ambar
    if umbral is None:
        return None, None

    serie_clean = serie.dropna()
    if serie_clean.empty:
        return None, None

    disparo = bool(op_fn(serie_clean, umbral).any())
    if not disparo:
        return False, None

    nivel = "ROJO" if umbral_rojo is not None else "AMBAR"
    motivo = MotivoSemaforo(
        descripcion=regla.get("descripcion", regla["variable"]),
        variable=regla["variable"],
        valor_observado=None,
        umbral_disparado=float(umbral),
        nivel=nivel,
        unidad=regla.get("unidad"),
        op=op_name,
    )
    return True, motivo


def _evaluar_reglas_franja(
    df: pd.DataFrame,
    actividad: dict[str, Any],
    fecha: date,
    franja_act: tuple[int, int],
) -> tuple[str, list[MotivoSemaforo], dict[str, float]]:
    """Núcleo de evaluación: aplica todas las reglas de la actividad
    usando ``franja_act`` como franja activa.

    Diseñado para ser reutilizable: ``evaluar_dia`` lo invoca con la
    franja_horaria completa de la actividad; ``calcular_ventanas_dia``
    lo invoca con sub-franjas deslizantes.

    Reglas con ``franja_especifica`` se intersectan con ``franja_act``.
    Si la intersección es vacía, la regla no se aplica.

    No genera avisos (los gestiona ``evaluar_dia``).
    """
    motivos: list[MotivoSemaforo] = []
    datos_clave: dict[str, float] = {}
    agregaciones_intentadas = 0
    agregaciones_con_datos = 0

    for regla in actividad.get("reglas", []):
        variable = regla["variable"]
        if variable in VARIABLES_DERIVADAS_PENDIENTES:
            continue
        if variable not in df.columns:
            continue

        # Resolver franja: intersección de franja_especifica con franja_act.
        if "franja_especifica" in regla:
            fe = regla["franja_especifica"]
            inicio = max(int(fe[0]), franja_act[0])
            fin = min(int(fe[1]), franja_act[1])
            if inicio > fin:
                continue  # no overlap
            franja = (inicio, fin)
        else:
            franja = franja_act

        sub = _filtrar_franja(df, fecha, franja)
        serie = sub[variable] if not sub.empty else pd.Series(dtype=float)

        flag_col = f"{variable}_estimada"
        es_estimada = False
        if flag_col in df.columns and not sub.empty:
            es_estimada = bool(sub[flag_col].fillna(False).any())

        agg_name = regla.get("agg")

        if agg_name == "cualquier_franja":
            agregaciones_intentadas += 1
            resultado, motivo = _evaluar_regla_cualquier_franja(serie, regla)
            if resultado is None:
                continue
            agregaciones_con_datos += 1
            datos_clave[f"{variable}_cualquier_franja"] = float(resultado)
            if motivo is not None:
                if es_estimada:
                    motivo.estimada = True
                motivos.append(motivo)
            continue

        if agg_name not in AGREGACIONES:
            continue

        agregaciones_intentadas += 1
        valor, motivo = _evaluar_regla_simple(serie, regla)
        if valor is None:
            continue
        agregaciones_con_datos += 1
        datos_clave[f"{variable}_{agg_name}"] = valor
        if motivo is not None:
            if es_estimada:
                motivo.estimada = True
            motivos.append(motivo)

    niveles = {m.nivel for m in motivos}
    if agregaciones_intentadas > 0 and agregaciones_con_datos == 0:
        semaforo = "SIN_DATOS"
    elif "ROJO" in niveles:
        semaforo = "ROJO"
    elif "AMBAR" in niveles:
        semaforo = "AMBAR"
    else:
        semaforo = "VERDE"

    return semaforo, motivos, datos_clave


def _construir_avisos(
    zona: dict[str, Any],
    actividad: dict[str, Any],
    fecha: date,
    df: pd.DataFrame,
) -> list[str]:
    """Genera la lista de avisos a nivel de zona/actividad/día.

    Incluye aviso de aludes (estacional) y "regla pendiente …" para
    cada regla con variable derivada no implementada o ausente del
    DataFrame.
    """
    avisos: list[str] = []

    if actividad.get("requiere_aviso_aludes") and fecha.month in MESES_AVISO_ALUDES:
        bol = zona.get("boletin_aludes") or {}
        nombre = bol.get("nombre")
        url = bol.get("url")
        if nombre and url:
            avisos.append(
                f"Consultar boletín de aludes oficial: {nombre} {url}"
            )

    for regla in actividad.get("reglas", []):
        variable = regla["variable"]
        descripcion = regla.get("descripcion", variable)
        if variable in VARIABLES_DERIVADAS_PENDIENTES:
            avisos.append(
                f"Regla pendiente: {descripcion} "
                "(variable derivada no implementada)"
            )
        elif variable not in df.columns:
            avisos.append(
                f"Regla pendiente: {descripcion} "
                f"(variable '{variable}' no disponible en datos)"
            )

    return avisos


# Ranking de "calidad" para identificar la sub-ventana MEJOR. Lower wins.
_RANK_MEJOR: dict[str, int] = {"VERDE": 0, "AMBAR": 1, "ROJO": 2, "SIN_DATOS": 3}
# Ranking de "gravedad" para identificar la sub-ventana PEOR. Lower wins
# (ROJO es la peor). SIN_DATOS se trata como "sin información actionable"
# y queda al final, para no robar el puesto a un ROJO real.
_RANK_PEOR: dict[str, int] = {"ROJO": 0, "AMBAR": 1, "VERDE": 2, "SIN_DATOS": 3}


def _solape(a: Ventana, b: Ventana) -> int:
    """Horas de solape entre dos sub-ventanas (fin exclusivo)."""
    return max(0, min(a.fin, b.fin) - max(a.inicio, b.inicio))


def calcular_ventanas_dia(
    prevision: PrevisionMeteo,
    actividad: dict[str, Any],
    fecha: date,
) -> VentanasDia:
    """Calcula la información de sub-ventanas del día (ADR-007 + ADR-009).

    Ventana deslizante de paso 1 h sobre la franja_horaria de la actividad.
    Cada posición se evalúa con las mismas reglas que el día completo.

    Política (ADR-009):

    1. Si la actividad no declara ``ventana_minima_h``: devuelve un
       VentanasDia vacío (todo None).
    2. Si la duración pedida es ≥ franja_horaria: una única ventana
       cubriendo la franja completa, expuesta como ``homogenea``.
    3. Si todas las sub-ventanas comparten el mismo semáforo: ``homogenea``
       poblada con la más temprana.
    4. En otro caso: ``mejor`` y ``peor`` poblados, eligiendo el par que
       minimiza el solape temporal. Desempates: (a) menor solape;
       (b) mejor más temprano; (c) peor más temprano.

    Las sub-ventanas SIN_DATOS no compiten por "mejor" ni "peor" cuando
    coexisten con semáforos válidos (se las excluye del ranking).
    """
    duracion_h = actividad.get("ventana_minima_h")
    if duracion_h is None:
        return VentanasDia(duracion_h=0)
    duracion_h = int(duracion_h)

    franja_act = actividad.get("franja_horaria", list(FRANJA_DEFAULT))
    franja_inicio, franja_fin = int(franja_act[0]), int(franja_act[1])
    franja_size = franja_fin - franja_inicio + 1  # ambos extremos inclusivos

    df = prevision.horario

    # Caso degenerado: ventana >= franja → única ventana, expuesta como
    # homogénea.
    if duracion_h >= franja_size:
        sem, motivos, dc = _evaluar_reglas_franja(
            df, actividad, fecha, (franja_inicio, franja_fin)
        )
        unica = Ventana(
            inicio=franja_inicio,
            fin=franja_inicio + duracion_h,  # exclusiva
            semaforo=sem,
            motivos=motivos,
            datos_clave=dc,
        )
        return VentanasDia(homogenea=unica, duracion_h=duracion_h)

    # Enumerar todas las sub-ventanas.
    ventanas: list[Ventana] = []
    last_start = franja_fin - duracion_h + 1
    for inicio in range(franja_inicio, last_start + 1):
        fin_inclusivo = inicio + duracion_h - 1
        sem, motivos, dc = _evaluar_reglas_franja(
            df, actividad, fecha, (inicio, fin_inclusivo)
        )
        ventanas.append(
            Ventana(
                inicio=inicio,
                fin=inicio + duracion_h,  # exclusiva
                semaforo=sem,
                motivos=motivos,
                datos_clave=dc,
            )
        )

    # Caso homogéneo estricto: todas las sub-ventanas mismo semáforo.
    semaforos_presentes = {v.semaforo for v in ventanas}
    if len(semaforos_presentes) == 1:
        return VentanasDia(homogenea=ventanas[0], duracion_h=duracion_h)

    # Para escoger mejor/peor, ignoramos SIN_DATOS si coexisten con
    # semáforos válidos (es información, no severidad).
    semaforos_validos = {s for s in semaforos_presentes if s != "SIN_DATOS"}
    if not semaforos_validos:
        # Solo SIN_DATOS (no debería pasar dado el filtro anterior, pero
        # por seguridad).
        return VentanasDia(homogenea=ventanas[0], duracion_h=duracion_h)

    sem_mejor = min(semaforos_validos, key=lambda s: _RANK_MEJOR[s])
    sem_peor = min(semaforos_validos, key=lambda s: _RANK_PEOR[s])

    # Si sólo hay un semáforo válido (p. ej. VERDE coexistiendo con
    # SIN_DATOS), no hay diferenciación: homogénea sobre el válido.
    if sem_mejor == sem_peor:
        candidata = next(v for v in ventanas if v.semaforo == sem_mejor)
        return VentanasDia(homogenea=candidata, duracion_h=duracion_h)

    candidatas_mejor = [v for v in ventanas if v.semaforo == sem_mejor]
    candidatas_peor = [v for v in ventanas if v.semaforo == sem_peor]

    # Construir pares y elegir el de mínimo solape. Desempate temprano.
    mejor, peor = min(
        (
            (m, p)
            for m in candidatas_mejor
            for p in candidatas_peor
        ),
        key=lambda mp: (_solape(mp[0], mp[1]), mp[0].inicio, mp[1].inicio),
    )

    return VentanasDia(
        mejor=mejor,
        peor=peor,
        duracion_h=duracion_h,
    )


def evaluar_dia(
    prevision: PrevisionMeteo,
    actividad: dict[str, Any],
    fecha: date,
) -> EvaluacionDia | None:
    """Evalúa una actividad concreta en una zona/fecha dadas.

    Devuelve ``None`` si la actividad no está activa en el mes de la
    fecha indicada (ver ``meses_activos`` en config/actividades.yaml,
    ADR-010). El consumidor (``main.py``, ``render.py``) debe omitir
    esa combinación zona/actividad/día.

    Si la actividad no declara ``meses_activos`` (compatibilidad), se
    considera activa todo el año.
    """
    meses_activos = actividad.get("meses_activos")
    if meses_activos is not None and fecha.month not in meses_activos:
        return None

    zona = prevision.zona
    df = prevision.horario
    franja_act = tuple(
        actividad.get("franja_horaria", FRANJA_DEFAULT)
    )  # type: ignore[assignment]

    avisos = _construir_avisos(zona, actividad, fecha, df)
    semaforo, motivos, datos_clave = _evaluar_reglas_franja(
        df, actividad, fecha, franja_act
    )
    ventanas = calcular_ventanas_dia(prevision, actividad, fecha)

    return EvaluacionDia(
        zona_id=zona["id"],
        actividad_id=actividad["id"],
        fecha=fecha,
        semaforo=semaforo,
        motivos=motivos,
        datos_clave=datos_clave,
        avisos=avisos,
        ventanas=ventanas,
    )
