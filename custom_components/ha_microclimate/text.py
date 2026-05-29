"""Support for Blynk text inputs.

Text entities allow string data entry:
- Current value read from coordinator.data (cached)
- Changes written via direct API call
- Optimistic cache update for instant UI feedback
- Special packed time helper for complex time formats
"""

import logging
import re

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlynkEntity
from .const import (
    CONF_ENABLED_BY_DEFAULT,
    CONF_PIN_NAME,
    CONF_PIN_TYPE,
    DOMAIN,
    INPUT_TEXT_MAX_LENGTH,
    INPUT_TEXT_MIN_LENGTH,
    PIN_TYPE_INPUT_TEXT,
    PIN_TYPE_PACKED_TIME_TEXT,
)

_LOGGER = logging.getLogger(__name__)


class BlynkText(BlynkEntity, TextEntity):
    """Representation of a Blynk text input."""

    def __init__(self, coordinator, api, pin, config):
        """Initialize the text input."""
        super().__init__(
            coordinator,
            pin,
            config[CONF_PIN_NAME],
            enabled_by_default=config.get(CONF_ENABLED_BY_DEFAULT, True),
        )
        self._api = api
        self._attr_native_min = config.get("min_length", INPUT_TEXT_MIN_LENGTH)
        self._attr_native_max = config.get("max_length", INPUT_TEXT_MAX_LENGTH)
        self._attr_pattern = config.get("pattern")
        self._attr_mode = "text"
        self._compiled_pattern = None

        if self._attr_pattern:
            try:
                self._compiled_pattern = re.compile(self._attr_pattern)
            except re.error:
                _LOGGER.warning(
                    "Ignoring invalid text pattern for %s: %s",
                    self._pin,
                    self._attr_pattern,
                )

    @property
    def native_value(self) -> str:
        """Return the current value from coordinator cache."""
        if not self.coordinator.data or self._pin not in self.coordinator.data:
            return ""

        value = str(self.coordinator.data[self._pin])
        _LOGGER.debug("Text input %s value from cache: %s", self._pin, value)
        return value

    async def async_set_value(self, value: str) -> None:
        """Set new value with optimistic update.
        
        Write pattern that doesn't disrupt polling:
        1. Async write to API (non-blocking, uses write lock)
        2. Optimistically update coordinator cache for instant UI feedback
        3. Write state to Home Assistant
        4. Next scheduled coordinator refresh confirms actual device state
        
        No manual refresh requested - avoids disrupting the polling schedule.
        """
        try:
            if self._compiled_pattern and not self._compiled_pattern.fullmatch(value):
                raise ValueError(
                    f"Value '{value}' does not match required pattern {self._attr_pattern}"
                )

            _LOGGER.debug("Setting text input %s to %s", self._pin, value)

            # Async write to device (non-blocking, uses persistent session)
            success = await self._api.set_pin_value(self._pin, value)

            if success:
                # Optimistic cache update for instant UI response
                if self.coordinator.data is not None:
                    self.coordinator.data[self._pin] = value
                self.async_write_ha_state()
            else:
                _LOGGER.warning("Failed to set text input %s to %s", self._pin, value)
        except Exception as err:
            _LOGGER.error("Error setting text value: %s", err)
            raise


class BlynkPackedTimeText(BlynkText):
    """Text helper that formats packed time values for easier editing."""

    _PACKED_RE = re.compile(r"^(?P<digits>\d+)(?P<tz>[A-Za-z_]+\/[A-Za-z_]+)(?P<flag>\d+)$")

    @classmethod
    def _decode_raw_value(cls, raw_value: str) -> tuple[list[str], str, str] | None:
        """Decode packed value into chunks, timezone, and flag."""
        match = cls._PACKED_RE.match(raw_value)
        if not match:
            return None

        digits = match.group("digits")
        timezone = match.group("tz")
        flag = match.group("flag")
        chunks = [digits[i : i + 2] for i in range(0, len(digits), 2)]
        return chunks, timezone, flag

    @classmethod
    def _encode_formatted_value(cls, value: str) -> str:
        """Accept either raw packed format or readable format and return packed value."""
        stripped = value.strip()
        if cls._PACKED_RE.match(stripped):
            return stripped

        parts = [part.strip() for part in stripped.split("|")]
        if len(parts) != 3:
            return stripped

        times_part, timezone, flag = parts
        tokens = [token for token in re.split(r"[\s,;]+", times_part) if token]
        normalized_tokens = []
        for token in tokens:
            token = token.replace(":", "")
            if token.isdigit():
                normalized_tokens.append(token)

        digits = "".join(normalized_tokens)
        if not digits or not flag.isdigit():
            return stripped

        return f"{digits}{timezone}{flag}"

    @property
    def native_value(self) -> str:
        """Return human-friendly value when the packed format is detected."""
        raw_value = super().native_value
        if not raw_value:
            return raw_value

        decoded = self._decode_raw_value(str(raw_value))
        if not decoded:
            return str(raw_value)

        chunks, timezone, flag = decoded
        times = " ".join(chunks)
        return f"{times} | {timezone} | {flag}"

    @property
    def extra_state_attributes(self):
        """Expose decoded packed value details as attributes."""
        attrs = {"pin": self._pin}
        if not self.coordinator.data or self._pin not in self.coordinator.data:
            return attrs

        raw_value = str(self.coordinator.data[self._pin])
        decoded = self._decode_raw_value(raw_value)
        if not decoded:
            attrs["raw_value"] = raw_value
            return attrs

        chunks, timezone, flag = decoded
        attrs.update(
            {
                "raw_value": raw_value,
                "time_chunks": chunks,
                "timezone": timezone,
                "flag": flag,
            }
        )
        return attrs

    async def async_set_value(self, value: str) -> None:
        """Allow setting readable values and convert them to packed format."""
        packed_value = self._encode_formatted_value(value)
        await super().async_set_value(packed_value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Blynk text inputs based on config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    pins_config = entry.data.get("pins", {})

    entities = []
    for pin, config in pins_config.items():
        pin_type = config.get(CONF_PIN_TYPE)
        if pin_type == PIN_TYPE_INPUT_TEXT:
            text_input = BlynkText(coordinator, api, pin, config)
            entities.append(text_input)
        elif pin_type == PIN_TYPE_PACKED_TIME_TEXT:
            text_input = BlynkPackedTimeText(coordinator, api, pin, config)
            entities.append(text_input)

    if entities:
        async_add_entities(entities)
