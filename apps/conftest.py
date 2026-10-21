"""Pytest glue for apps/*/backend/test_*.py.

Run from backend/: `.venv/bin/python -m pytest tests ../apps -q`.
Puts backend/ on sys.path (so tests can import `app` / `portal_platform`)
and reuses the shared ``client`` / ``login`` fixtures from
backend/tests/conftest.py.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.conftest import client, login  # noqa: E402,F401
