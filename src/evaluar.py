"""Lógica pura de evaluación de actividades en función de la previsión.

Sin I/O, sin red, sin escritura. Recibe ``PrevisionMeteo`` (de
``src.fetch``) y un dict de actividad (de ``config/actividades.yaml``)
y devuelve una ``EvaluacionDia``.

Reglas resumen:
- Cada actividad declara una lista de reglas. Cada regla = variable
  + agregación + operador + umbral(es) ámbar/rojo.
- El peor componente determina el semáforo del día: ROJO > AMBAR > VERDE.
- Reglas con ``op == "informativo"`` solo reportan, no afectan al color.
- Variables derivadas (snowfall_48h_previas, indice_tormenta) se saltan
  y se añade un aviso pendiente.
- Si la previsión no tiene datos para la fecha (más allá del horizonte
  del modelo), el semáforo es ``SIN_DATOS`` (extensión a la spec — ver
  ADR-003).
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

# Variables declaradas en actividades.yaml que aún no se calculan
# (semanas 2 y 4). Cualquier regla que las referencie se salta y se
# añade un aviso.
VARIABLES_DERIVADAS_PENDIENTES: set[str] = {
    "snowfall_48h_previas",
    "indice_tormenta",
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
class EvaluacionDia:
    zona_id: str
    actividad_id: str
    fecha: date
    semaforo: str  # "VERDE" | "AMBAR" | "ROJO" | "SIN_DATOS"
    motivos: list[MotivoSemaforo] = field(default_factory=list)
    datos_clave: dict[str, float] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


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


def evaluar_dia(
    prevision: PrevisionMeteo,
    actividad: dict[str, Any],
    fecha: date,
) -> EvaluacionDia:
    """Evalúa una actividad concreta en una zona/fecha dadas."""
    zona = prevision.zona
    df = prevision.horario
    franja_act = tuple(
        actividad.get("franja_horaria", FRANJA_DEFAULT)
    )  # type: ignore[assignment]

    motivos: list[MotivoSemaforo] = []
    datos_clave: dict[str, float] = {}
    avisos: list[str] = []

    # Aviso de aludes (cabecera de zona).
    if actividad.get("requiere_aviso_aludes") and fecha.month in MESES_AVISO_ALUDES:
        bol = zona.get("boletin_aludes") or {}
        nombre = bol.get("nombre")
        url = bol.get("url")
        if nombre and url:
            avisos.append(
                f"Consultar boletín de aludes oficial: {nombre} {url}"
            )

    agregaciones_intentadas = 0
    agregaciones_con_datos = 0

    for regla in actividad.get("reglas", []):
        variable = regla["variable"]
        descripcion = regla.get("descripcion", variable)

        # 1) Variables derivadas no implementadas en Semana 2.
        if variable in VARIABLES_DERIVADAS_PENDIENTES:
            avisos.append(
                f"Regla pendiente: {descripcion} "
                "(variable derivada no implementada)"
            )
            continue

        # 2) Variable no presente en el DataFrame.
        if variable not in df.columns:
            avisos.append(
                f"Regla pendiente: {descripcion} "
                f"(variable '{variable}' no disponible en datos)"
            )
            continue

        # 3) Resolver franja.
        franja = tuple(regla.get("franja_especifica", franja_act))

        sub = _filtrar_franja(df, fecha, franja)
        serie = sub[variable] if not sub.empty else pd.Series(dtype=float)

        # Detección genérica: si existe la columna ``<variable>_estimada``
        # y al menos una fila de la franja es True, el motivo derivado
        # de esa regla se marca como estimado.
        flag_col = f"{variable}_estimada"
        es_estimada = False
        if flag_col in df.columns and not sub.empty:
            es_estimada = bool(sub[flag_col].fillna(False).any())

        agg_name = regla.get("agg")

        # 4) Caso especial: cualquier_franja.
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

        # 5) Agregaciones pandas estándar.
        if agg_name not in AGREGACIONES:
            avisos.append(
                f"Regla pendiente: {descripcion} "
                f"(agregación '{agg_name}' no soportada)"
            )
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

    # Determinar semáforo final.
    niveles = {m.nivel for m in motivos}
    if agregaciones_intentadas > 0 and agregaciones_con_datos == 0:
        semaforo = "SIN_DATOS"
    elif "ROJO" in niveles:
        semaforo = "ROJO"
    elif "AMBAR" in niveles:
        semaforo = "AMBAR"
    else:
        semaforo = "VERDE"

    return EvaluacionDia(
        zona_id=zona["id"],
        actividad_id=actividad["id"],
        fecha=fecha,
        semaforo=semaforo,
        motivos=motivos,
        datos_clave=datos_clave,
        avisos=avisos,
    )
