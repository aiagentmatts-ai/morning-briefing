"""Structural validator for data/morning.json.

Catches malformed briefing artifacts the local Claude Desktop scheduled task
may have produced. This is a structural check only — it cannot detect
fabricated stories or invented numeric facts. Schema-level guards stay in
this script; data-integrity guards live in CLAUDE.md as authoring rules.

Scoped to morning briefings; the evening briefing pipeline uses a different
shape (weather/calendar/tasks vs sections) and isn't actively producing
artifacts yet. Extend `validate()` and accept type='evening' when that goes live.

Run:
    python scripts/validate-briefing.py data/morning.json

Exits 0 if the file validates; exits 1 and prints every error otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_TOP_LEVEL = {
    "date": str,
    "type": str,
    "generated_at": str,
    "sections": list,
}

REQUIRED_SECTION = {
    "id": str,
    "label": str,
    "count": int,
    "stories": list,
}

REQUIRED_STORY = {
    "headline": str,
    "summary": str,
    "source": str,
}


def _check_iso_date(value: str, path: str, errors: list[str]) -> None:
    if not ISO_DATE.match(value):
        errors.append(f"{path}: expected YYYY-MM-DD, got {value!r}")
        return
    try:
        date.fromisoformat(value)
    except ValueError as e:
        errors.append(f"{path}: not a valid calendar date ({e})")


def _check_iso_datetime(value: str, path: str, errors: list[str]) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError as e:
        errors.append(f"{path}: not parseable as ISO datetime ({e})")


def _check_types(obj: dict[str, Any], spec: dict[str, type], path: str, errors: list[str]) -> None:
    for key, expected in spec.items():
        if key not in obj:
            errors.append(f"{path}.{key}: missing required field")
            continue
        if not isinstance(obj[key], expected):
            errors.append(
                f"{path}.{key}: expected {expected.__name__}, got {type(obj[key]).__name__}"
            )


def _check_non_empty_str(obj: dict[str, Any], key: str, path: str, errors: list[str]) -> None:
    if key not in obj or not isinstance(obj[key], str):
        return  # type error already reported by _check_types
    if not obj[key].strip():
        errors.append(f"{path}.{key}: empty string (use 'note' field on the section if feed is unavailable)")


def validate(data: Any, source: str) -> list[str]:
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"{source}: top-level value must be an object, got {type(data).__name__}"]

    _check_types(data, REQUIRED_TOP_LEVEL, source, errors)

    if isinstance(data.get("date"), str):
        _check_iso_date(data["date"], f"{source}.date", errors)

    if isinstance(data.get("type"), str) and data["type"] not in {"morning", "evening"}:
        errors.append(f"{source}.type: expected 'morning' or 'evening', got {data['type']!r}")

    if isinstance(data.get("generated_at"), str):
        _check_iso_datetime(data["generated_at"], f"{source}.generated_at", errors)

    sections = data.get("sections")
    if isinstance(sections, list):
        if not sections:
            errors.append(f"{source}.sections: empty list — briefing must have at least one section")
        for i, section in enumerate(sections):
            sp = f"{source}.sections[{i}]"
            if not isinstance(section, dict):
                errors.append(f"{sp}: expected object, got {type(section).__name__}")
                continue
            _check_types(section, REQUIRED_SECTION, sp, errors)
            _check_non_empty_str(section, "id", sp, errors)
            _check_non_empty_str(section, "label", sp, errors)

            stories = section.get("stories")
            count = section.get("count")
            if isinstance(stories, list) and isinstance(count, int) and count != len(stories):
                errors.append(
                    f"{sp}: count={count} but stories has length {len(stories)} — must match"
                )

            if isinstance(stories, list):
                for j, story in enumerate(stories):
                    stp = f"{sp}.stories[{j}]"
                    if not isinstance(story, dict):
                        errors.append(f"{stp}: expected object, got {type(story).__name__}")
                        continue
                    _check_types(story, REQUIRED_STORY, stp, errors)
                    _check_non_empty_str(story, "headline", stp, errors)
                    _check_non_empty_str(story, "summary", stp, errors)
                    _check_non_empty_str(story, "source", stp, errors)

    return errors


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: validate_briefing.py FILE [FILE ...]", file=sys.stderr)
        return 2

    total_errors = 0
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"{path}: file not found", file=sys.stderr)
            total_errors += 1
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"{path}: invalid JSON ({e})", file=sys.stderr)
            total_errors += 1
            continue

        errors = validate(data, str(path))
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            total_errors += len(errors)
        else:
            print(f"{path}: OK")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
