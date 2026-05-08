"""Fixture-driven tests for scripts/scrape-pjm-markets.py.

Same shape as tests/test_palegis.py: assertions run against a snapshotted
HTML page committed at tests/fixtures/pjm/markets-and-operations.html.
Ground-truth values were verified by hand on www.pjm.com when the fixture
was captured. When pjm.com legitimately changes upstream (new zone, new
fuel category, layout change), regenerate the fixture with
`python scripts/refetch-fixtures.py` and update assertions that shift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scrape_pjm_markets as sp

FIXTURE = Path(__file__).parent / "fixtures" / "pjm" / "markets-and-operations.html"


@pytest.fixture(scope="module")
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Today's Outlook — four headline numbers
# ---------------------------------------------------------------------------

def test_todays_outlook_has_required_keys(html):
    o = sp.parse_todays_outlook(html)
    for k in ("currentLoadMw", "forecastedPeakMw", "rtoLmpDollars", "tomorrowPeakMw"):
        assert k in o, f"Today's Outlook missing key {k!r}; got {sorted(o)}"


def test_todays_outlook_values(html):
    """Snapshotted from pjm.com/markets-and-operations on 2026-05-07.

    These numbers will drift on every refetch (load and LMP change minute-to-
    minute), but the parser should extract them exactly off the fixture HTML.
    If a refetched fixture has different values, the assertions below need to
    be updated to whatever the new fixture HTML actually shows.
    """
    o = sp.parse_todays_outlook(html)
    assert o["currentLoadMw"] == 88595
    assert o["forecastedPeakMw"] == 85302
    assert o["rtoLmpDollars"] == 68.29
    assert o["tomorrowPeakMw"] == 81928


def test_todays_outlook_as_of_present(html):
    """Should populate asOf with the 'HH:MM x.m. EPT' timestamp PJM stamps
    onto the page (stable across refetches modulo the actual time)."""
    o = sp.parse_todays_outlook(html)
    assert "asOf" in o
    assert "EPT" in o["asOf"]


def test_todays_outlook_value_types(html):
    o = sp.parse_todays_outlook(html)
    assert isinstance(o["currentLoadMw"], int)
    assert isinstance(o["forecastedPeakMw"], int)
    assert isinstance(o["rtoLmpDollars"], float)
    assert isinstance(o["tomorrowPeakMw"], int)
    # Sanity ranges — PJM peaks are typically 65-150 GW.
    assert 30_000 <= o["currentLoadMw"] <= 200_000
    assert 30_000 <= o["forecastedPeakMw"] <= 200_000


# ---------------------------------------------------------------------------
# Zone LMP table — must include all 4 PA zones plus the PJM-RTO benchmark
# ---------------------------------------------------------------------------

def test_zone_lmps_returns_all_pa_zones(html):
    """All four PA-territory zones must appear, plus the PJM-RTO line."""
    z = sp.parse_zone_lmps(html)
    for required in ("METED", "PECO", "PENELEC", "PPL", "PJM-RTO"):
        assert required in z, f"zone {required!r} missing from LMP table; got {sorted(z)}"


def test_zone_lmps_count(html):
    """Snapshot count — 22 zones in the Zones tab fixture (AECO, AEP, APS,
    ATSI, BGE, COMED, DAY, DEOK, DOM, DPL, DUQ, EKPC, JCPL, METED, OVEC,
    PECO, PENELEC, PEPCO, PJM-RTO, PPL, PSEG, RECO). PJM occasionally adds
    or drops zones, so this pins the count to what was live at snapshot
    and surfaces meaningful additions as a test failure to triage."""
    z = sp.parse_zone_lmps(html)
    assert len(z) == 22


def test_zone_lmps_specific_values(html):
    """Spot-checks on the snapshotted fixture's exact prices.
    All four PA zones plus the PJM-RTO benchmark."""
    z = sp.parse_zone_lmps(html)
    assert z["PJM-RTO"] == 68.29
    assert z["PPL"] == 67.89
    assert z["PSEG"] == 68.91
    assert z["PENELEC"] == 68.47
    assert z["METED"] == 69.18
    assert z["PECO"] == 68.38


def test_zone_pjm_rto_matches_outlook_rto(html):
    """The PJM-RTO row in the zone LMP table should match the RTO LMP
    headline in Today's Outlook — they're the same number rendered twice.
    A divergence means one of the two parsers is reading the wrong field."""
    z = sp.parse_zone_lmps(html)
    o = sp.parse_todays_outlook(html)
    assert z["PJM-RTO"] == o["rtoLmpDollars"]


def test_zone_lmps_all_floats(html):
    z = sp.parse_zone_lmps(html)
    for zone, price in z.items():
        assert isinstance(price, float), f"{zone}: {price!r} not float"
        # PJM LMPs are typically -50 to 1000 in normal conditions; widely
        # outside that range likely indicates a parser misread.
        assert -200 <= price <= 5000, f"{zone}: ${price} outside plausible LMP range"


def test_no_zone_with_empty_name(html):
    z = sp.parse_zone_lmps(html)
    assert all(name.strip() for name in z), "blank zone name in LMP table"


# ---------------------------------------------------------------------------
# Fuel mix — Highcharts JSON inside inline <script>
# ---------------------------------------------------------------------------

def test_fuel_mix_shape(html):
    f = sp.parse_fuel_mix(html)
    assert "byFuel" in f
    assert "totalMw" in f
    assert isinstance(f["byFuel"], list)
    assert isinstance(f["totalMw"], int)


def test_fuel_mix_count(html):
    f = sp.parse_fuel_mix(html)
    # PJM's all-fuels chart pins to 10 categories: Coal, Gas, Hydro,
    # Multiple Fuels, Nuclear, Oil, Other Renewables, Solar, Storage, Wind.
    assert len(f["byFuel"]) == 10


def test_fuel_mix_includes_known_fuels(html):
    f = sp.parse_fuel_mix(html)
    names = {entry["name"] for entry in f["byFuel"]}
    for required in ("Coal", "Gas", "Nuclear", "Solar", "Wind", "Hydro"):
        assert required in names, f"fuel {required!r} missing; got {sorted(names)}"


def test_fuel_mix_specific_values(html):
    """Snapshotted MW for 2026-05-07 8:55 p.m. EPT. These will shift on
    refetch — they're here to detect parser regressions, not as a permanent
    contract on PJM dispatch."""
    f = sp.parse_fuel_mix(html)
    by_name = {entry["name"]: entry["mw"] for entry in f["byFuel"]}
    assert by_name["Coal"] == 11455
    assert by_name["Gas"] == 30200
    assert by_name["Nuclear"] == 29605
    assert by_name["Solar"] == 2099


def test_fuel_mix_total_matches_visible_total(html):
    """The visible 'Total: X MW' div should equal the sum of the per-fuel
    MWs from the Highcharts series. If they diverge, the parser is reading
    one of the two from the wrong place."""
    f = sp.parse_fuel_mix(html)
    derived = sum(entry["mw"] for entry in f["byFuel"])
    assert f["totalMw"] == derived
    assert f["totalMw"] == 84857  # snapshot ground truth


def test_fuel_mix_renewables_subset(html):
    f = sp.parse_fuel_mix(html)
    assert "renewablesMw" in f
    assert f["renewablesMw"] == 10115  # snapshot ground truth
    # Renewables must be a strict subset of total.
    assert f["renewablesMw"] < f["totalMw"]


def test_fuel_mix_all_mw_non_negative(html):
    f = sp.parse_fuel_mix(html)
    for entry in f["byFuel"]:
        assert isinstance(entry["mw"], int)
        assert entry["mw"] >= 0, f"{entry['name']}: negative MW {entry['mw']}"


# ---------------------------------------------------------------------------
# build_record — the orchestrated output JSON shape
# ---------------------------------------------------------------------------

def test_build_record_shape(html):
    rec = sp.build_record(html, "2026-05-07T20:55:00Z")
    for k in ("lastSync", "source", "todaysOutlook", "zoneLmps", "fuelMix"):
        assert k in rec, f"build_record missing key {k!r}"
    assert rec["source"] == sp.URL
    assert rec["lastSync"] == "2026-05-07T20:55:00Z"


def test_build_record_zone_list_flags_pa_zones(html):
    rec = sp.build_record(html, "now")
    pa_flagged = {z["zone"] for z in rec["zoneLmps"] if z["isPaZone"]}
    assert pa_flagged == {"METED", "PECO", "PENELEC", "PPL"}


def test_build_record_zone_list_sorted(html):
    rec = sp.build_record(html, "now")
    zones = [z["zone"] for z in rec["zoneLmps"]]
    assert zones == sorted(zones), f"zoneLmps not alphabetized: {zones}"


def test_build_record_zone_entries_have_required_fields(html):
    rec = sp.build_record(html, "now")
    for z in rec["zoneLmps"]:
        assert set(z.keys()) == {"zone", "lmpDollars", "isPaZone"}
        assert isinstance(z["zone"], str) and z["zone"]
        assert isinstance(z["lmpDollars"], float)
        assert isinstance(z["isPaZone"], bool)


# ---------------------------------------------------------------------------
# Hub LMPs — Western Hub is THE PA wholesale benchmark; assertions pin
# WESTERN/EASTERN/NJ/DOMINION as the PA-NJ-relevant set, plus the count.
# ---------------------------------------------------------------------------

def test_hub_lmps_returns_pa_nj_relevant_hubs(html):
    h = sp.parse_hub_lmps(html)
    for required in ("WESTERN HUB", "EASTERN HUB", "NEW JERSEY HUB", "DOMINION HUB"):
        assert required in h, f"hub {required!r} missing from LMP table; got {sorted(h)}"


def test_hub_lmps_count(html):
    """Snapshot count — 12 hubs in the fixture (AEP GEN HUB, AEP-DAYTON HUB,
    ATSI GEN HUB, CHICAGO GEN HUB, CHICAGO HUB, DOMINION HUB, EASTERN HUB,
    N ILLINOIS HUB, NEW JERSEY HUB, OHIO HUB, WEST INT HUB, WESTERN HUB).
    PJM occasionally adds or drops hubs; pinning the count surfaces those
    as a test failure for triage."""
    h = sp.parse_hub_lmps(html)
    assert len(h) == 12


def test_hub_lmps_specific_values(html):
    """Snapshotted from the fixture. WESTERN HUB is the PA trading benchmark."""
    h = sp.parse_hub_lmps(html)
    assert h["WESTERN HUB"] == 44.78
    assert h["EASTERN HUB"] == 45.52
    assert h["NEW JERSEY HUB"] == 44.80
    assert h["DOMINION HUB"] == 44.11


def test_hub_lmps_all_floats(html):
    h = sp.parse_hub_lmps(html)
    for hub, price in h.items():
        assert isinstance(price, float), f"{hub}: {price!r} not float"
        assert -200 <= price <= 5000, f"{hub}: ${price} outside plausible LMP range"


def test_hub_and_zone_tables_are_distinct(html):
    """The Hubs tab should not contain any of the utility-zone names; if it
    does, the parser is reading from the wrong tab."""
    z = sp.parse_zone_lmps(html)
    h = sp.parse_hub_lmps(html)
    assert not (set(z) & set(h)), f"zone/hub overlap: {set(z) & set(h)}"


def test_build_record_includes_hub_lmps(html):
    rec = sp.build_record(html, "now")
    assert "hubLmps" in rec
    pa_nj_flagged = {x["hub"] for x in rec["hubLmps"] if x["isPaNjHub"]}
    assert pa_nj_flagged == {"WESTERN HUB", "EASTERN HUB", "NEW JERSEY HUB", "DOMINION HUB"}


def test_build_record_hub_entries_have_required_fields(html):
    rec = sp.build_record(html, "now")
    for hub in rec["hubLmps"]:
        assert set(hub.keys()) == {"hub", "lmpDollars", "isPaNjHub"}
        assert isinstance(hub["hub"], str) and hub["hub"]
        assert isinstance(hub["lmpDollars"], float)
        assert isinstance(hub["isPaNjHub"], bool)


def test_build_record_hub_list_sorted(html):
    rec = sp.build_record(html, "now")
    names = [h["hub"] for h in rec["hubLmps"]]
    assert names == sorted(names), f"hubLmps not alphabetized: {names}"


# ---------------------------------------------------------------------------
# Defensive — parser should fail loudly on a malformed page, not silently
# produce empty/zero data
# ---------------------------------------------------------------------------

def test_parse_todays_outlook_raises_on_missing_block():
    with pytest.raises(ValueError, match="Today's Outlook"):
        sp.parse_todays_outlook("<html><body><h1>Maintenance</h1></body></html>")


def test_parse_zone_lmps_raises_on_missing_tab():
    with pytest.raises(ValueError, match="pricing-tab-zones"):
        sp.parse_zone_lmps("<html><body></body></html>")


def test_parse_hub_lmps_raises_on_missing_tab():
    with pytest.raises(ValueError, match="pricing-tab-hubs"):
        sp.parse_hub_lmps("<html><body></body></html>")


def test_parse_fuel_mix_raises_on_missing_chart():
    with pytest.raises(ValueError, match="createChartgfmchartallfuels"):
        sp.parse_fuel_mix("<html><body></body></html>")
