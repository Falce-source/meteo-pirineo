"""Variables meteorológicas derivadas calculadas localmente.

Cubre:
    - ``freezing_level_height``: ARPEGE no lo sirve, se aproxima desde
      ``temperature_2m`` con lapse rate estándar 6.5 K/km (ADR-005).
    - ``indice_tormenta``: índice 0-3 calculado a partir de CAPE,
      weathercode WMO, precipitación y humedad (ADR-006).

Para cualquier variable derivada que sustituya una columna del modelo,
añadir también la columna ``<variable>_estimada`` (bool) para que el
render pueda etiquetar el valor como aproximación.
"""

from __future__ import annotations

import pandas as pd

from src.tormenta import calcular_indice_tormenta

# Gradiente adiabático estándar (lapse rate), K/m. Valor típico
# usado en montaña para tropósfera libre / aire saturado.
LAPSE_RATE_C_PER_M: float = 6.5 / 1000


def calcular_freezing_level_height(
    df_horario: pd.DataFrame,
    elevacion_zona_m: float,
) -> pd.Series:
    """Estima la altura del cero térmico en metros.

    Asume gradiente adiabático constante: por cada grado positivo a
    cota ``elevacion_zona_m``, el cero térmico está
    ``1 / LAPSE_RATE_C_PER_M`` metros más arriba.

    Aproximación de primer orden. NO sustituye al FLH directo del
    modelo cuando esté disponible.

    Args:
        df_horario: DataFrame con columna ``temperature_2m`` (°C).
        elevacion_zona_m: Elevación de referencia de la zona, en metros.

    Returns:
        Serie de FLH en metros con el mismo índice que ``df_horario``.
    """
    return elevacion_zona_m + (
        df_horario["temperature_2m"] / LAPSE_RATE_C_PER_M
    )


def enriquecer_con_derivadas(
    df_horario: pd.DataFrame,
    elevacion_zona_m: float,
) -> pd.DataFrame:
    """Devuelve copia del DataFrame con las variables derivadas añadidas.

    - ``freezing_level_height``: sobrescrito con el valor calculado
      (la columna venía como NaN desde ARPEGE).
    - ``freezing_level_height_estimada``: bool ``True`` en todas las
      filas, para que el render marque el valor como aproximado.

    Las variables originales (temperatura, viento, etc.) no se tocan.
    """
    df = df_horario.copy()
    df["freezing_level_height"] = calcular_freezing_level_height(
        df, elevacion_zona_m
    )
    df["freezing_level_height_estimada"] = True
    df["indice_tormenta"] = calcular_indice_tormenta(df)
    df["indice_tormenta_estimada"] = True
    return df
