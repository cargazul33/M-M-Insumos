"""Punto de entrada compatible con el workflow histórico (python app.py).

Equivale a `python -m radar`.
"""
from radar.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
