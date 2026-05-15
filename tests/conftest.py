"""Pytest setup — load hyphen-named scripts as importable modules.

Production scripts use hyphens so GitHub Actions can invoke them directly
(`python scripts/scrape-pjm-markets.py`), but Python module names can't
contain hyphens. We load each one via importlib under an underscore name
so tests can `from scrape_pjm_markets import ...` / `from validate_briefing import ...`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, script_relpath: str) -> None:
    script_path = REPO_ROOT / script_relpath
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {script_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


_load("scrape_pjm_markets", "scripts/scrape-pjm-markets.py")
_load("validate_briefing", "scripts/validate-briefing.py")
