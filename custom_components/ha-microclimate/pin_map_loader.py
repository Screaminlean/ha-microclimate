"""Helpers for loading generated pin map metadata."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from .const import PIN_TYPE_SENSOR

_LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_pin_map() -> dict[str, dict[str, Any]]:
    """Load pin metadata generated from docs/Evo_Blynk_Pins.csv."""
    pin_map_path = Path(__file__).with_name("pin_map.json")
    if not pin_map_path.exists():
        return {}

    try:
        payload = json.loads(pin_map_path.read_text(encoding="utf-8"))
    except Exception as err:
        _LOGGER.warning("Failed to load pin map %s: %s", pin_map_path, err)
        return {}

    pins = payload.get("pins")
    if not isinstance(pins, dict):
        return {}
    return pins


def get_pin_defaults(pin: str) -> dict[str, Any]:
    """Return metadata defaults for a single pin."""
    return load_pin_map().get(pin.upper(), {})


def get_default_pin_type(pin: str) -> str:
    """Return suggested pin type from metadata, if any."""
    return str(get_pin_defaults(pin).get("default_pin_type", PIN_TYPE_SENSOR))


def get_select_mapping(pin: str) -> dict[str, str]:
    """Return select value-label mapping for a pin."""
    raw_mapping = get_pin_defaults(pin).get("select_options", {})
    if not isinstance(raw_mapping, dict):
        return {}

    return {str(value): str(label) for value, label in raw_mapping.items()}
