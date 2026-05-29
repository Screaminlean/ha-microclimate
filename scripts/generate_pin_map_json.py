"""Generate pin_map.json from docs/Evo_Blynk_Pins.csv."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ENUM_PATTERN = re.compile(r"\((?P<inner>[^)]*)\)")
PAIR_PATTERN = re.compile(r"(?P<value>\d+)\s*=\s*(?P<label>[^=]+?)(?=\s+\d+\s*=|$)")

VALID_PIN_TYPES = {
    "sensor",
    "binary_sensor",
    "switch",
    "input_number",
    "button",
    "input_text",
    "select",
    "packed_time_text",
}

PIN_TYPE_ALIASES = {
    "binary": "binary_sensor",
    "number": "input_number",
    "text": "input_text",
    "packeddate": "packed_time_text",
    "packed_date": "packed_time_text",
    "packed_time": "packed_time_text",
}

DATE_DD_MM_PATTERN = r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[0-2])$"


def parse_select_options(description: str) -> dict[str, str]:
    """Extract enum pairs like (0=Fixed 1=Heating 2=Cooling)."""
    match = ENUM_PATTERN.search(description)
    if not match:
        return {}

    inner = match.group("inner")
    options: dict[str, str] = {}
    for pair in PAIR_PATTERN.finditer(inner):
        value = pair.group("value").strip()
        label = pair.group("label").strip()
        if value:
            options[value] = label
    return options


def infer_default_type(description: str, select_options: dict[str, str]) -> str | None:
    """Infer an entity type from description text."""
    lower_desc = description.lower()
    if select_options:
        return "select"
    if "season" in lower_desc and "start time" in lower_desc:
        return "packed_time_text"
    if "name" in lower_desc:
        return "input_text"
    return None


def infer_text_pattern(description: str, pin_type: str | None) -> str | None:
    """Infer a validation pattern for text pins from description text."""
    if pin_type != "input_text":
        return None

    if "start date dd/mm" in description.lower():
        return DATE_DD_MM_PATTERN

    return None


def normalize_pin_type(raw_type: str) -> str | None:
    """Normalize CSV type values to integration pin type constants."""
    normalized = raw_type.strip().lower().replace(" ", "_")
    if not normalized:
        return None

    normalized = PIN_TYPE_ALIASES.get(normalized, normalized)
    if normalized not in VALID_PIN_TYPES:
        allowed = ", ".join(sorted(VALID_PIN_TYPES))
        raise ValueError(f"Unsupported pin type '{raw_type}'. Allowed values: {allowed}")
    return normalized


def parse_show_in_ui(raw_hidden: str) -> bool:
    """Convert Hidden CSV column to show_in_ui boolean."""
    normalized = raw_hidden.strip().lower()
    if not normalized:
        return True

    if normalized in {"true", "yes", "1", "hidden", "hide"}:
        return False
    if normalized in {"false", "no", "0", "visible", "show", "shown"}:
        return True

    raise ValueError(
        f"Unsupported hidden value '{raw_hidden}'. Use true/false (or hidden/visible)."
    )


def build_pin_map(csv_path: Path) -> dict[str, dict[str, object]]:
    """Build pin map payload from CSV rows."""
    pins: dict[str, dict[str, object]] = {}

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pin = (row.get("PIN") or "").strip().upper()
            description = (row.get("Description") or "").strip()
            if not pin or not description:
                continue

            explicit_pin_type = normalize_pin_type(row.get("Type") or "")
            raw_hidden = row.get("Hidden") or row.get("Expose") or ""
            show_in_ui = parse_show_in_ui(raw_hidden)
            select_options = parse_select_options(description)
            default_pin_type = explicit_pin_type or infer_default_type(description, select_options)
            text_pattern = infer_text_pattern(description, default_pin_type)

            payload: dict[str, object] = {
                "description": description,
                "show_in_ui": show_in_ui,
            }
            if default_pin_type:
                payload["default_pin_type"] = default_pin_type
            if text_pattern:
                payload["pattern"] = text_pattern
            if select_options:
                payload["select_options"] = select_options

            pins[pin] = payload

    return {
        "source": str(csv_path.as_posix()),
        "pins": pins,
    }


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("docs/Evo_Blynk_Pins.csv"),
        help="Path to source CSV",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("custom_components/ha_microclimate/pin_map.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    payload = build_pin_map(args.csv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} with {len(payload['pins'])} mapped pins")


if __name__ == "__main__":
    main()
