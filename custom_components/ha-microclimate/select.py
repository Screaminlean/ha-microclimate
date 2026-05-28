"""Support for Blynk select entities.

Select entities are writable dropdowns that use coordinator cache:
- Current option read from coordinator.data (no API polling)
- Option changes use direct API calls
- Optimistic cache updates for immediate UI response
- Value-to-label mapping for user-friendly display
"""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlynkEntity
from .const import (
    CONF_PIN_NAME,
    CONF_PIN_TYPE,
    DOMAIN,
    PIN_TYPE_SELECT,
)
from .pin_map_loader import get_select_mapping

_LOGGER = logging.getLogger(__name__)


class BlynkSelect(BlynkEntity, SelectEntity):
    """Representation of a Blynk select input."""

    def __init__(self, coordinator, api, pin, config):
        """Initialize select entity."""
        super().__init__(coordinator, pin, config[CONF_PIN_NAME])
        self._api = api

        known_options = get_select_mapping(self._pin)
        custom_values = config.get("select_values")
        custom_options = config.get("select_options")

        # Option source priority: user-defined mapping -> known pin mapping -> safe numeric fallback.
        if custom_values and custom_options and len(custom_values) == len(custom_options):
            self._value_to_label = {
                str(value): str(label)
                for value, label in zip(custom_values, custom_options)
            }
        elif known_options:
            self._value_to_label = dict(known_options)
        else:
            self._value_to_label = {"0": "0", "1": "1"}

        # Keep both directions for efficient read/write conversion.
        self._label_to_value = {label: value for value, label in self._value_to_label.items()}
        self._attr_options = list(self._label_to_value.keys())

    @property
    def current_option(self) -> str | None:
        """Return current selected option label from coordinator cache.
        
        Reads raw value from coordinator.data and translates it to
        user-friendly label. No API call is made here.
        """
        if not self.coordinator.data or self._pin not in self.coordinator.data:
            return None

        raw_value = str(self.coordinator.data[self._pin])
        if raw_value in self._value_to_label:
            return self._value_to_label[raw_value]

        # If the device reports an unknown value, expose it as an ad-hoc option
        # so Home Assistant can still display and round-trip the live state.
        if raw_value not in self._label_to_value:
            self._label_to_value[raw_value] = raw_value
            self._value_to_label[raw_value] = raw_value
            self._attr_options = list(self._label_to_value.keys())

        return raw_value

    async def async_select_option(self, option: str) -> None:
        """Change selected option with optimistic update.
        
        Write pattern that doesn't disrupt polling:
        1. Convert UI label to raw device value
        2. Async write to API (non-blocking, uses write lock)
        3. Optimistically update coordinator cache for instant UI feedback
        4. Write state to Home Assistant
        5. Next scheduled coordinator refresh confirms actual device state
        
        No manual refresh requested - avoids disrupting the polling schedule.
        """
        # UI label is converted back to the raw value expected by the device
        raw_value = self._label_to_value.get(option, option)
        _LOGGER.debug("Setting select %s to %s (raw %s)", self._pin, option, raw_value)

        # Async write to device (non-blocking, uses persistent session)
        success = await self._api.set_pin_value(self._pin, raw_value)
        
        if success:
            # Optimistic cache update for instant UI response
            if self.coordinator.data is not None:
                self.coordinator.data[self._pin] = raw_value
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Failed to set select %s to %s", self._pin, option)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Blynk select entities based on config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    pins_config = entry.data.get("pins", {})

    entities = []
    for pin, config in pins_config.items():
        # Only create select entities for pins configured as select type.
        if config.get(CONF_PIN_TYPE) == PIN_TYPE_SELECT:
            entities.append(BlynkSelect(coordinator, api, pin, config))

    if entities:
        async_add_entities(entities)
