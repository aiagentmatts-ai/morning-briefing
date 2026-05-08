"""Pytest setup for the PJM market scraper tests.

The production script lives at `scripts/scrape-pjm-markets.py` (hyphen, so
the GitHub Actions workflow can invoke it as `python scripts/scrape-pjm-markets.py`),
but Python module names can't contain hyphens. This loads it via importlib
under the name `scrape_pjm_markets` so tests can `from scrape_pjm_markets import ...`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_PATH = REPO_ROOT / "scripts" / "scrape-pjm-markets.py"


def _load_scraper():
    spec = importlib.util.spec_from_file_location("scrape_pjm_markets", SCRAPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRAPER_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scrape_pjm_markets"] = mod
    spec.loader.exec_module(mod)
    return mod


_load_scraper()
