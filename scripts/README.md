# scripts/

Scripts puntuales de validación y exploración. **No son código de producción**: no se importan desde `src/`, no tienen tests, y pueden borrarse cuando dejen de aportar valor.

Se ejecutan desde la raíz del repo, p. ej.:

```bash
python scripts/validar_viento_elevacion.py
python scripts/comparar_modelos.py
```

Cada script documenta su propósito en su docstring inicial.
