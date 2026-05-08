#!/usr/bin/env python3
"""
Refetch fixtures under tests/fixtures/<source>/ from their live source URLs.

Each subdirectory of tests/fixtures/ has a MANIFEST.json that maps fixture
filenames to source URLs (and an optional structural-signature config).
Currently used by:
  - tests/fixtures/pjm/        — scripts/scrape-pjm-markets.py

Two modes:

    python scripts/refetch-fixtures.py
        Overwrite each fixture file with fresh HTML from the source URL.
        Use this when the source legitimately changed (new committee, new
        zone, layout redesign) and the parser tests need to be re-pointed
        at current ground truth. Inspect the diff in `git status` after,
        commit only if reasonable, and update assertions in tests/test_*.py
        for any ground-truth values that shifted.

    python scripts/refetch-fixtures.py --diff-only
        Fetch each source URL, compare structurally against the saved
        fixture, and exit non-zero if structure differs. The nightly
        drift workflows use this mode — they do NOT auto-update fixtures,
        because a real source change might silently break parse semantics
        and a human needs to look at it.

    python scripts/refetch-fixtures.py --source pjm
        Restrict to one source dir (skip the others). Forward-compatible
        for additional source dirs added later.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"
USER_AGENT = "pa-ga-guide-fixture-refresher/1.0 (+https://github.com/aiagentmatts-ai)"
TIMEOUT = 30

# Per-source structural-signature selector lists. Each entry maps a fixture
# source-dir name to the CSS selectors and substring checks the drift detector
# applies. Keep this list narrow — it should match exactly the structural hooks
# the parsers in scripts/scrape-*.py depend on. Don't pad it with extra
# selectors "for safety": false positives there would page a human every time
# any unrelated DOM element on the page changes.
SIGNATURE_CONFIG: dict[str, dict] = {
    "pjm": {
        "selectors": [
            "#moTodaysOutlook",
            ".todaysoutlookvalcol",
            ".todaysoutlookvalcol1",
            "#pricing-tab-zones",
            "#pricing-tab-zones ul.lmp-price-table",
            "#pricing-tab-zones ul.lmp-price-table li",
            "#pricing-tab-hubs",
            "#pricing-tab-hubs ul.lmp-price-table",
            "#pricing-tab-hubs ul.lmp-price-table li",
            ".div-gen-fuel-mix-total",
            ".div-gen-fuel-mix-total .container-gen-total",
        ],
        "substrings": {
            "fuel_mix_chart_function": ["function createChartgfmchartallfuels"],
        },
        "href_counts": {},
    },
}


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def structural_signature(html: str, config: dict) -> dict:
    """Reduce an HTML doc to a structural fingerprint that ignores volatile
    text content but trips on anything the parser actually depends on.
    """
    s = BeautifulSoup(html, "lxml")
    sig: dict = {sel: len(s.select(sel)) for sel in config["selectors"]}
    for key, needles in config.get("substrings", {}).items():
        sig[key] = all(n in html for n in needles)
    for key, needle in config.get("href_counts", {}).items():
        sig[f"{key}_count"] = sum(
            1 for a in s.find_all("a", href=True) if needle in a["href"]
        )
    return sig


def discover_sources(filter_name: str | None) -> list[tuple[str, Path, dict]]:
    """Walk tests/fixtures/* for MANIFEST.json files. Returns
    [(source_name, source_dir, manifest_dict), ...]. Filters to a single
    source if filter_name is set."""
    out: list[tuple[str, Path, dict]] = []
    if not FIXTURE_ROOT.exists():
        print(f"fixture root missing: {FIXTURE_ROOT}", file=sys.stderr)
        sys.exit(1)
    for child in sorted(FIXTURE_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if filter_name and child.name != filter_name:
            continue
        manifest_path = child / "MANIFEST.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        out.append((child.name, child, manifest))
    if filter_name and not out:
        print(f"no fixtures dir matching --source={filter_name!r}", file=sys.stderr)
        sys.exit(1)
    return out


def cmd_refetch(sources: list[tuple[str, Path, dict]]) -> int:
    total = 0
    for name, src_dir, manifest in sources:
        print(f"== {name} ==", file=sys.stderr)
        for filename, entry in manifest["fixtures"].items():
            url = entry["url"]
            path = src_dir / filename
            print(f"  fetch {url}", file=sys.stderr)
            try:
                html = fetch(url)
            except requests.RequestException as e:
                print(f"  ! failed: {e}", file=sys.stderr)
                return 2
            path.write_text(html, encoding="utf-8")
            total += 1
    print(f"Wrote {total} fixtures across {len(sources)} sources.", file=sys.stderr)
    return 0


def cmd_diff_only(sources: list[tuple[str, Path, dict]]) -> int:
    drift: list[str] = []
    for name, src_dir, manifest in sources:
        config = SIGNATURE_CONFIG.get(name)
        if config is None:
            print(f"  ! no signature config for source {name!r}; skipping drift check", file=sys.stderr)
            continue
        print(f"== {name} ==", file=sys.stderr)
        for filename, entry in manifest["fixtures"].items():
            url = entry["url"]
            path = src_dir / filename
            if not path.exists():
                drift.append(f"{name}/{filename}: fixture missing on disk")
                continue
            try:
                live_html = fetch(url)
            except requests.RequestException as e:
                print(f"  ! fetch failed for {name}/{filename}: {e}", file=sys.stderr)
                continue
            saved_sig = structural_signature(path.read_text(encoding="utf-8"), config)
            live_sig = structural_signature(live_html, config)
            diffs = [k for k in saved_sig if saved_sig[k] != live_sig.get(k)]
            if diffs:
                drift.append(
                    f"{name}/{filename}: structural change in {diffs} "
                    f"(saved={ {k:saved_sig[k] for k in diffs} }, "
                    f"live={ {k:live_sig.get(k) for k in diffs} })"
                )
    if drift:
        print("DRIFT DETECTED:", file=sys.stderr)
        for d in drift:
            print(f"  - {d}", file=sys.stderr)
        return 1
    print("No structural drift.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refetch fixtures from live sources.")
    p.add_argument(
        "--diff-only",
        action="store_true",
        help="Fetch live and compare structural signature against saved fixtures; exit 1 on drift.",
    )
    p.add_argument(
        "--source",
        default=None,
        help="Restrict to one source subdirectory of tests/fixtures/ (e.g. 'palegis', 'pjm'). Default: all.",
    )
    args = p.parse_args(argv)
    sources = discover_sources(args.source)
    if args.diff_only:
        return cmd_diff_only(sources)
    return cmd_refetch(sources)


if __name__ == "__main__":
    sys.exit(main())
