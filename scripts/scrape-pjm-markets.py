#!/usr/bin/env python3
"""
Daily PJM market snapshot scraper.

Pulls Today's Outlook (current load, forecasted peak, RTO LMP, tomorrow's
peak), the zone LMP table (PA zones METED / PECO / PENELEC / PPL plus the
rest of the PJM footprint), the trading-hub LMP table (Western Hub —
the canonical PA wholesale benchmark — plus Eastern Hub, NJ Hub, Dominion
Hub, etc.), and the generation fuel mix from www.pjm.com/markets-and-operations
and writes the result to data/energy-markets.json.

The PJM markets page server-renders all three blocks — the LMP table is a
plain <ul class="lmp-price-table">, Today's Outlook values are <h2> tags
inside .todaysoutlookvalcol divs, and the fuel mix is a Highcharts options
JSON literal inside an inline <script>. No API key is required and no
JavaScript runtime is needed at scrape time.

Run daily via .github/workflows/refresh-energy-markets.yml. Locally:

    python scripts/scrape-pjm-markets.py             # writes data/energy-markets.json
    python scripts/scrape-pjm-markets.py --dry-run   # writes to ./.scrape-output/ instead

This file is the greenfield twin of scripts/scrape-palegis.py — it was
written with the harden-scraper pattern in mind from the start, so the
parse functions below are pure and the test suite at tests/test_pjm.py
asserts every contract here against a snapshotted fixture.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

URL = "https://www.pjm.com/markets-and-operations"
USER_AGENT = "Mozilla/5.0 (compatible; daily-briefing-energy-fetcher/1.0; +https://github.com/aiagentmatts-ai/Briefings)"
REQUEST_TIMEOUT = 30

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_PATH = REPO_ROOT / "data" / "energy-markets.json"

# PA zones we care about for the briefing — the full table includes JCPL, PEPCO,
# RECO, OVEC, EKPC etc. as well, and the scraper returns ALL of them. This list
# is just for the convenience flag "isPaZone" on each entry.
PA_ZONES = {"METED", "PECO", "PENELEC", "PPL"}

# Hubs whose LMPs matter most for PA/NJ co-op wholesale settlement. Western
# Hub is THE primary PA trading benchmark; Eastern + NJ are the eastern-half
# benchmarks; Dominion is the VA/southern-PA benchmark. The scraper returns
# ALL hubs (12 in the fixture); this set just drives the isPaHub convenience flag.
PA_NJ_HUBS = {"WESTERN HUB", "EASTERN HUB", "NEW JERSEY HUB", "DOMINION HUB"}


# -- HTTP -----------------------------------------------------------------

def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# -- Parsers --------------------------------------------------------------

_NUMBER_RE = re.compile(r"-?\$?[\d,]+(?:\.\d+)?")


def _to_int(s: str) -> int:
    return int(s.replace(",", "").replace("$", "").strip())


def _to_float(s: str) -> float:
    return float(s.replace(",", "").replace("$", "").strip())


def parse_todays_outlook(html: str) -> dict:
    """Read the four headline numbers from the 'Today's Outlook' block.

    The page renders each metric as <h2>VALUE</h2> followed by a small label
    inside a .todaysoutlookvalcol div. We find each label and pull the <h2>
    immediately above it. This is more robust than positional indexing — if
    PJM reorders the columns, label-based lookup still finds the right number.
    """
    s = soup(html)
    outlook_block = s.find(id="moTodaysOutlook")
    if outlook_block is None:
        raise ValueError("'Today's Outlook' block not found on PJM markets page")

    out: dict = {}

    # 'As of HH:MM x.m. EPT' — the line right below the Today's Outlook header.
    header = outlook_block.find(class_="motodaysoutlookheadercol")
    if header is not None:
        m = re.search(r"As of\s+(\d{1,2}:\d{2}\s*[ap]\.?m\.?\s*EPT)", header.get_text(" ", strip=True), re.I)
        if m:
            out["asOf"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # The four .todaysoutlookvalcol divs are in fixed visual order: current
    # load, forecasted peak, RTO LMP, shortage pricing flag, PAH flag.
    for col in outlook_block.select(".todaysoutlookvalcol"):
        text = col.get_text(" ", strip=True)
        h2 = col.find("h2")
        h2_text = h2.get_text(" ", strip=True) if h2 else ""
        # 'current load (MW)' / 'forecasted peak (MW)'
        if "current load" in text.lower():
            out["currentLoadMw"] = _to_int(h2_text)
        elif "forecasted peak" in text.lower():
            out["forecastedPeakMw"] = _to_int(h2_text)
        elif "rto lmp" in text.lower():
            out["rtoLmpDollars"] = _to_float(h2_text)
        # Shortage pricing / PAH cols don't carry numeric headlines we surface.

    # Tomorrow's peak forecast lives in a sibling .todaysoutlookvalcol1.
    for col in outlook_block.select(".todaysoutlookvalcol1"):
        text = col.get_text(" ", strip=True)
        h2 = col.find("h2")
        if h2 and "peak" in text.lower():
            out["tomorrowPeakMw"] = _to_int(h2.get_text(" ", strip=True))

    return out


def _parse_lmp_tab(html: str, tab_id: str) -> dict:
    """Walk every <ul class="lmp-price-table"> inside the given tab div and
    return {name: lmp_dollars}. The PJM markets page splits each tab into a
    two-column layout (2 ULs per tab), so we concatenate.

    Used by both parse_zone_lmps (#pricing-tab-zones) and parse_hub_lmps
    (#pricing-tab-hubs). The schema of each <li> is two <div>s: name on the
    left, dollar-prefixed LMP on the right.
    """
    s = soup(html)
    tab = s.find(id=tab_id)
    if tab is None:
        raise ValueError(f"LMP tab not found on PJM markets page (#{tab_id} missing)")
    out: dict = {}
    for table in tab.find_all("ul", class_="lmp-price-table"):
        for li in table.find_all("li"):
            divs = li.find_all("div")
            if len(divs) < 2:
                continue
            name = divs[0].get_text(" ", strip=True)
            val = divs[1].get_text(" ", strip=True)
            if not name or not val:
                continue
            try:
                out[name] = _to_float(val)
            except ValueError:
                # Defensive: skip a row that doesn't parse as currency rather
                # than failing the whole scrape.
                continue
    return out


def parse_zone_lmps(html: str) -> dict:
    """Extract the zone LMP tables from the 'Zones' tab (utility service-area
    LMPs: METED/PECO/PENELEC/PPL + neighboring zones + the PJM-RTO benchmark).

    The PJM markets page has three tabs of LMP data:
      #pricing-tab-zones       — utility service-area LMPs (this fn)
      #pricing-tab-hubs        — trading-hub LMPs (parse_hub_lmps)
      #pricing-tab-interfaces  — external-intertie LMPs (NYIS, MISO, etc.;
                                  not surfaced — relevant only to transmission
                                  analysts, not to PA/NJ co-op briefing)
    """
    return _parse_lmp_tab(html, "pricing-tab-zones")


def parse_hub_lmps(html: str) -> dict:
    """Extract trading-hub LMPs from the 'Hubs' tab (#pricing-tab-hubs).

    Hubs are the price points wholesale energy contracts settle against —
    Western Hub in particular is the canonical PA trading benchmark. For a
    PA/NJ co-op briefing these are arguably more decision-relevant than the
    utility-zone LMPs above: when an REA member negotiates a wholesale
    supply contract or hedges a position, Western Hub is the index.

    Returns {hub_name: lmp_dollars} (e.g. 'WESTERN HUB' -> 44.78).
    """
    return _parse_lmp_tab(html, "pricing-tab-hubs")


def parse_fuel_mix(html: str) -> dict:
    """Extract per-fuel MW from the createChartgfmchartallfuels Highcharts JSON.

    The page emits a function body like:
        function createChartgfmchartallfuels() {
          var ChartOptions = { ..., "series":[{"data":[
              {"y":11455,"name":"Coal","color":"#663399"},
              {"y":30200,"name":"Gas",...}, ... ]}], ...
          };
          new Highcharts.chart(...);
        }
    We pull out the ChartOptions JSON object literal (it's strict JSON) and
    read series[0].data. Plus we read the visible 'Total: X MW' / 'Renewables:
    Y MW' values inside .div-gen-fuel-mix-total — they're a redundant cross-
    check on the per-fuel sum.
    """
    m = re.search(
        r"function createChartgfmchartallfuels\(\)\s*\{\s*var\s+ChartOptions\s*=\s*(\{.*?\});\s*new\s+Highcharts",
        html,
        re.S,
    )
    if not m:
        raise ValueError("createChartgfmchartallfuels function not found on PJM markets page")
    chart = json.loads(m.group(1))

    series = chart.get("series") or []
    if not series:
        raise ValueError("ChartOptions.series is empty")
    by_fuel: list[dict] = []
    for entry in series[0].get("data") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        y = entry.get("y")
        if not isinstance(name, str) or not isinstance(y, (int, float)):
            continue
        by_fuel.append({"name": name, "mw": int(y)})

    # The .div-gen-fuel-mix-total block has Total + Renewables MW lines.
    s = soup(html)
    totals: dict = {}
    total_block = s.find("div", class_="div-gen-fuel-mix-total")
    if total_block is not None:
        for row in total_block.select("div.container-gen-total"):
            label = row.find("div", class_="left")
            value = row.find("div", class_="right")
            if not label or not value:
                continue
            ltxt = label.get_text(" ", strip=True).rstrip(":").lower()
            vtxt = value.get_text(" ", strip=True)
            m = _NUMBER_RE.search(vtxt)
            if not m:
                continue
            try:
                totals[ltxt] = _to_int(m.group(0))
            except ValueError:
                continue

    out: dict = {"byFuel": by_fuel}
    if "total" in totals:
        out["totalMw"] = totals["total"]
    else:
        out["totalMw"] = sum(f["mw"] for f in by_fuel)
    if "renewables" in totals:
        out["renewablesMw"] = totals["renewables"]
    return out


# -- Orchestration --------------------------------------------------------

def build_record(html: str, last_sync: str) -> dict:
    outlook = parse_todays_outlook(html)
    zone_lmps_raw = parse_zone_lmps(html)
    hub_lmps_raw = parse_hub_lmps(html)
    fuel_mix = parse_fuel_mix(html)

    # Normalize zoneLmps + hubLmps into lists of objects (easier for JS to
    # iterate) with PA-relevance flags. The briefing UI can highlight PA
    # zones / PA-NJ hubs without hardcoding the membership sets.
    zone_lmps = [
        {
            "zone": name,
            "lmpDollars": price,
            "isPaZone": name in PA_ZONES,
        }
        for name, price in sorted(zone_lmps_raw.items())
    ]
    hub_lmps = [
        {
            "hub": name,
            "lmpDollars": price,
            "isPaNjHub": name in PA_NJ_HUBS,
        }
        for name, price in sorted(hub_lmps_raw.items())
    ]

    return {
        "_comment": "PJM market snapshot scraped from pjm.com/markets-and-operations. Server-rendered widget data. Refreshed daily by .github/workflows/refresh-energy-markets.yml. Do not edit by hand — overlays should live in a separate file if ever needed.",
        "lastSync": last_sync,
        "source": URL,
        "todaysOutlook": outlook,
        "zoneLmps": zone_lmps,
        "hubLmps": hub_lmps,
        "fuelMix": fuel_mix,
    }


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scrape pjm.com/markets-and-operations into data/energy-markets.json.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH,
                   help="Path to write JSON (default: data/energy-markets.json)")
    p.add_argument("--dry-run", action="store_true",
                   help="Write to ./.scrape-output/energy-markets.json instead of --out.")
    args = p.parse_args(list(argv) if argv is not None else None)

    out_path = (Path("./.scrape-output").resolve() / "energy-markets.json") if args.dry_run else args.out

    print(f"Fetching {URL} ...", file=sys.stderr)
    html = fetch(URL)
    record = build_record(html, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}", file=sys.stderr)
    western = next((h["lmpDollars"] for h in record["hubLmps"] if h["hub"] == "WESTERN HUB"), None)
    print(
        f"  current load: {record['todaysOutlook'].get('currentLoadMw')} MW; "
        f"RTO LMP: ${record['todaysOutlook'].get('rtoLmpDollars')}; "
        f"Western Hub: ${western}; "
        f"zones: {len(record['zoneLmps'])}; hubs: {len(record['hubLmps'])}; "
        f"fuels: {len(record['fuelMix']['byFuel'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
