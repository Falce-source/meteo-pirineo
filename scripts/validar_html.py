"""Sanity-check del HTML generado en docs/index.html.

Script desechable, ejecutado tras ``python -m src.main``.
Verifica: tamaño razonable, número de celdas, ausencia de recursos
externos, lista de IDs únicos.

Ejecutar desde la raíz del repo:
    python scripts/validar_html.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HTML_PATH = Path("docs/index.html")
TAMANO_MAX_KB = 200
CELDAS_ESPERADAS = 50  # 2 zonas × 5 actividades × 5 días

# Regexes sencillas; el HTML lo escribimos nosotros y es predecible.
RE_CELDA = re.compile(
    r'<button[^>]*\bclass="celda[^"]*"',
    re.IGNORECASE,
)
RE_CELDA_ID = re.compile(
    r'<button[^>]*\bid="([^"]+)"[^>]*\bclass="celda',
    re.IGNORECASE,
)
RE_LINK_EXT = re.compile(
    r'<link\b[^>]*\brel="stylesheet"[^>]*\bhref="(?:https?:|//)[^"]*"',
    re.IGNORECASE,
)
RE_SCRIPT_EXT = re.compile(
    r'<script\b[^>]*\bsrc="(?:https?:|//)[^"]*"',
    re.IGNORECASE,
)


def main() -> int:
    if not HTML_PATH.exists():
        print(f"ERROR: no existe {HTML_PATH}. Ejecuta 'python -m src.main' primero.")
        return 1

    raw = HTML_PATH.read_bytes()
    contenido = raw.decode("utf-8")
    tamano_kb = len(raw) / 1024

    celdas = RE_CELDA.findall(contenido)
    ids = RE_CELDA_ID.findall(contenido)
    refs_externas = (
        RE_LINK_EXT.findall(contenido) + RE_SCRIPT_EXT.findall(contenido)
    )

    print(f"Archivo:               {HTML_PATH}")
    print(f"Tamaño:                {tamano_kb:.1f} KB")
    print(f"Celdas <button.celda>: {len(celdas)} (esperadas: {CELDAS_ESPERADAS})")
    print(f"Referencias externas:  {len(refs_externas)} (esperadas: 0)")

    fallos: list[str] = []
    if tamano_kb >= TAMANO_MAX_KB:
        fallos.append(f"tamaño {tamano_kb:.1f} KB ≥ {TAMANO_MAX_KB} KB")
    if len(celdas) != CELDAS_ESPERADAS:
        fallos.append(
            f"#celdas={len(celdas)} ≠ {CELDAS_ESPERADAS}"
        )
    if refs_externas:
        fallos.append(f"{len(refs_externas)} referencias externas")
    if len(ids) != len(set(ids)):
        dup = [i for i in ids if ids.count(i) > 1]
        fallos.append(f"IDs duplicados: {set(dup)}")

    print()
    print(f"IDs únicos de celdas ({len(set(ids))}):")
    for cid in sorted(set(ids)):
        print(f"  - {cid}")

    print()
    if fallos:
        print("RESULTADO: FAIL")
        for f in fallos:
            print(f"  * {f}")
        return 2
    print("RESULTADO: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
