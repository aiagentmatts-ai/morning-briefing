"""Tests for scripts/validate-briefing.py.

The validator runs on every push to main that touches data/*.json and nightly
as a safety net. These tests pin down what counts as a malformed briefing so
the watchdog/validator distinction stays clear:

- watchdog: did a briefing land at all today? (commit existence)
- validator: is the briefing that landed structurally sane? (this script)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import validate_briefing as v

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_MORNING = REPO_ROOT / "data" / "sample-morning.json"
LIVE_MORNING = REPO_ROOT / "data" / "morning.json"

# Note: sample-evening.json uses a different schema (weather/calendar/tasks
# instead of sections) and no evening.json artifact is being produced yet.
# Extend the validator to handle "evening" type when that pipeline goes live.


def _valid_minimal() -> dict:
    return {
        "date": "2026-05-14",
        "type": "morning",
        "generated_at": "2026-05-14T08:00:00-04:00",
        "sections": [
            {
                "id": "national-politics",
                "label": "National Politics",
                "count": 1,
                "stories": [
                    {
                        "headline": "Headline",
                        "summary": "Summary text.",
                        "source": "Source",
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Happy path — committed sample fixtures and the current live briefing
# should all validate cleanly. If a real briefing ever fails these, the
# validator caught what it was meant to.
# ---------------------------------------------------------------------------

def test_minimal_valid_briefing_passes():
    assert v.validate(_valid_minimal(), "test") == []


def test_sample_morning_validates():
    data = json.loads(SAMPLE_MORNING.read_text(encoding="utf-8"))
    assert v.validate(data, str(SAMPLE_MORNING)) == []


@pytest.mark.skipif(not LIVE_MORNING.exists(), reason="no live morning.json yet")
def test_live_morning_validates():
    """Locks in that the most recently committed briefing is structurally sane.

    If this fails locally, the next briefing run will fail the push-time
    validate-briefing workflow — fix the briefing artifact, not this test.
    """
    data = json.loads(LIVE_MORNING.read_text(encoding="utf-8"))
    assert v.validate(data, str(LIVE_MORNING)) == []


# ---------------------------------------------------------------------------
# Structural errors — one assertion per failure mode the validator must catch
# ---------------------------------------------------------------------------

def test_top_level_not_object():
    errors = v.validate([], "x")
    assert any("top-level value must be an object" in e for e in errors)


def test_missing_date():
    data = _valid_minimal()
    del data["date"]
    errors = v.validate(data, "x")
    assert any("x.date: missing required field" in e for e in errors)


def test_bad_date_format():
    data = _valid_minimal()
    data["date"] = "May 14, 2026"
    errors = v.validate(data, "x")
    assert any("expected YYYY-MM-DD" in e for e in errors)


def test_invalid_calendar_date():
    data = _valid_minimal()
    data["date"] = "2026-02-30"
    errors = v.validate(data, "x")
    assert any("not a valid calendar date" in e for e in errors)


def test_bad_type():
    data = _valid_minimal()
    data["type"] = "midday"
    errors = v.validate(data, "x")
    assert any("expected 'morning' or 'evening'" in e for e in errors)


def test_bad_generated_at():
    data = _valid_minimal()
    data["generated_at"] = "yesterday"
    errors = v.validate(data, "x")
    assert any("not parseable as ISO datetime" in e for e in errors)


def test_empty_sections_rejected():
    data = _valid_minimal()
    data["sections"] = []
    errors = v.validate(data, "x")
    assert any("empty list" in e for e in errors)


def test_count_mismatch_with_stories():
    data = _valid_minimal()
    data["sections"][0]["count"] = 5  # but only 1 story
    errors = v.validate(data, "x")
    assert any("count=5 but stories has length 1" in e for e in errors)


def test_empty_section_stories_allowed():
    """Per CLAUDE.md: empty stories array is OK if feed is down.

    The watchdog/validator must not punish honest empty-list reporting —
    fabrication is the failure mode, not "feed was unreachable today."
    """
    data = _valid_minimal()
    data["sections"][0]["count"] = 0
    data["sections"][0]["stories"] = []
    assert v.validate(data, "x") == []


def test_story_missing_required_field():
    data = _valid_minimal()
    del data["sections"][0]["stories"][0]["source"]
    errors = v.validate(data, "x")
    assert any("stories[0].source: missing required field" in e for e in errors)


def test_story_empty_headline_rejected():
    data = _valid_minimal()
    data["sections"][0]["stories"][0]["headline"] = "   "
    errors = v.validate(data, "x")
    assert any("stories[0].headline: empty string" in e for e in errors)


def test_section_id_must_be_non_empty():
    data = _valid_minimal()
    data["sections"][0]["id"] = ""
    errors = v.validate(data, "x")
    assert any("sections[0].id: empty string" in e for e in errors)


def test_multiple_errors_reported_together():
    """Validator must not stop at first error — surface all of them so the
    watchdog issue body has the complete picture."""
    data = _valid_minimal()
    data["date"] = "bad"
    data["type"] = "lunch"
    del data["generated_at"]
    errors = v.validate(data, "x")
    assert len(errors) >= 3
