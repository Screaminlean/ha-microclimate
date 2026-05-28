"""Generate pin_map.json from docs/Evo_Blynk_Pins.csv."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ENUM_PATTERN = re.compile(r"\((?P<inner>[^)]*)\)")
PAIR_PATTERN = re.compile(r"(?P<value>\d+)\s*=\s*(?P<label>[^=]+?)(?=\s+\d+\s*=|$)")


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

            select_options = parse_select_options(description)
            default_pin_type = infer_default_type(description, select_options)

            payload: dict[str, object] = {
                "description": description,
            }
            if default_pin_type:
                payload["default_pin_type"] = default_pin_type
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
