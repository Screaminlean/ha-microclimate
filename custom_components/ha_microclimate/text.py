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
    """Text helper that formats packed time values for easier editing.
    
    The Microclimate device encodes times in a packed format:
    - Format: {time1}\0{time2}\0{timezone}\0{flag} (null byte separated)
    - Each time is encoded as a 5-digit number representing seconds from midnight
    - Example: 27000 = 27000 seconds = 7.5 hours = 07:30
    - Display format: HH:MM
    - Input formats accepted: "HH:MM" or raw packed format
    """

    # Regex to match null-byte-separated packed time format
    _PACKED_RE = re.compile(r"^(?P<times>[\d\x00]+)(?P<tz>[A-Za-z_/]+)\x00(?P<flag>\d+)$")

    @classmethod
    def _decode_time_value(cls, seconds_str: str) -> str:
        """Decode a 5-digit seconds value to HH:MM format.
        
        Args:
            seconds_str: 5-digit string representing seconds from midnight (e.g., "27000")
            
        Returns:
            Time in HH:MM format (e.g., "07:30")
        """
        try:
            total_seconds = int(seconds_str)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, ZeroDivisionError):
            return seconds_str

    @classmethod
    def _encode_time_value(cls, time_str: str) -> str:
        """Encode HH:MM format to 5-digit seconds value.
        
        Args:
            time_str: Time in HH:MM format (e.g., "07:30")
            
        Returns:
            5-digit seconds string (e.g., "27000")
        """
        try:
            time_str = time_str.strip()
            
            # Parse HH:MM format
            if ":" in time_str:
                parts = time_str.split(":")
                hours = int(parts[0])
                minutes = int(parts[1])
            elif len(time_str) == 4 and time_str.isdigit():
                # Parse HHMM format
                hours = int(time_str[:2])
                minutes = int(time_str[2:4])
            else:
                return time_str
            
            # Validate time
            if not (0 <= hours < 24 and 0 <= minutes < 60):
                return time_str
            
            # Encode: (hours * 3600) + (minutes * 60) = seconds from midnight
            total_seconds = (hours * 3600) + (minutes * 60)
            return f"{total_seconds:05d}"
        except (ValueError, IndexError):
            return time_str

    @classmethod
    def _decode_raw_value(cls, raw_value: str) -> tuple[list[str], str, str] | None:
        """Decode packed value into time strings, timezone, and flag.
        
        Returns:
            (list of HH:MM times, timezone, flag) or None if invalid
        """
        # Strip whitespace that might cause matching issues
        raw_value = raw_value.strip()
        
        _LOGGER.debug("Attempting to decode packed time value: '%s' (length: %d)", raw_value, len(raw_value))
        
        match = cls._PACKED_RE.match(raw_value)
        if not match:
            _LOGGER.warning(
                "Failed to match packed time regex for value: '%s'. "
                "Expected format: {time}\\0{time}\\0{timezone}\\0{flag}",
                raw_value
            )
            return None

        times_section = match.group("times")
        timezone = match.group("tz")
        flag = match.group("flag")
        
        # Split the times section by null bytes and decode each
        time_strings = times_section.rstrip('\x00').split('\x00')
        times = []
        for time_str in time_strings:
            if time_str:  # Skip empty strings
                decoded_time = cls._decode_time_value(time_str)
                times.append(decoded_time)
                _LOGGER.debug("Decoded time chunk '%s' to '%s'", time_str, decoded_time)
        
        _LOGGER.debug(
            "Successfully decoded: times=%s, timezone='%s', flag='%s'",
            times, timezone, flag
        )
        
        return times, timezone, flag

    @classmethod
    def _encode_formatted_value(cls, value: str) -> str:
        """Accept HH:MM format or raw format and return packed value.
        
        Accepted input formats:
        - Raw packed format: "27000\027000\0Europe/London\00"
        - Full format: "07:30 | Europe/London | 0"
        - Multiple times: "07:30, 19:00 | Europe/London | 0"
        """
        stripped = value.strip()
        
        # If already in packed format, return as-is
        if cls._PACKED_RE.match(stripped):
            return stripped

        # Try to parse as "HH:MM | timezone | flag" format
        if "|" in stripped:
            parts = [part.strip() for part in stripped.split("|")]
            if len(parts) == 3:
                times_part, timezone, flag = parts
                
                # Extract and encode all times (comma or space separated)
                time_tokens = [t.strip() for t in re.split(r"[,;\s]+", times_part) if t.strip() and ":" in t]
                encoded_times = []
                
                for time_token in time_tokens:
                    encoded = cls._encode_time_value(time_token)
                    # Ensure 5 digits
                    if encoded.isdigit():
                        encoded_times.append(encoded.zfill(5))
                
                # Build packed format with null byte separators
                if encoded_times and flag.isdigit():
                    times_section = "\x00".join(encoded_times)
                    return f"{times_section}\x00{timezone}\x00{flag}"
        
        # If just a time like "07:30", we can't encode without timezone/flag
        return stripped

    @property
    def native_value(self) -> str:
        """Return human-friendly time in HH:MM format."""
        raw_value = super().native_value
        if not raw_value:
            return raw_value

        decoded = self._decode_raw_value(str(raw_value))
        if not decoded:
            return str(raw_value)

        times, timezone, flag = decoded
        
        # For a single time, just show the time
        if len(times) == 1:
            return times[0]
        
        # For multiple times, remove duplicates but preserve order
        unique_times = []
        for time in times:
            if time not in unique_times:
                unique_times.append(time)
        
        # If all times were the same, just show one
        if len(unique_times) == 1:
            return unique_times[0]
        
        # Otherwise show them comma-separated
        return ", ".join(unique_times)

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
            attrs["friendly_format"] = "Unable to decode"
            return attrs

        times, timezone, flag = decoded
        attrs.update(
            {
                "raw_value": raw_value,
                "decoded_times": times,
                "timezone": timezone,
                "flag": flag,
                "friendly_format": f"{', '.join(times)} ({timezone})",
            }
        )
        return attrs

    async def async_set_value(self, value: str) -> None:
        """Allow setting time values in HH:MM format.
        
        Accepted formats:
        - "07:30" - Single time (preserves existing timezone/flag)
        - "07:30 | Europe/London | 0" - Full format
        - "07:30, 19:00 | Europe/London | 0" - Multiple times
        - "2700027000Europe/London0" - Raw packed format
        """
        # If user provides just a time, we need to preserve timezone/flag
        if not self._PACKED_RE.match(value) and "|" not in value:
            # Get current value to extract timezone and flag
            current_raw = str(self.coordinator.data.get(self._pin, ""))
            decoded_current = self._decode_raw_value(current_raw)
            
            if decoded_current:
                _, timezone, flag = decoded_current
                # Reconstruct with new time but existing timezone/flag
                value = f"{value} | {timezone} | {flag}"
        
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
