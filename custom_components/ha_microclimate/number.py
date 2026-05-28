"""Support for Blynk number inputs.

Number entities are writable and use a hybrid approach:
- State reads from coordinator.data (cached, no API overhead)
- Commands use direct API calls for immediate response
- Optimistic updates to coordinator.data for instant UI feedback
- Next coordinator refresh confirms actual device state
"""

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlynkEntity
from .const import (
    DOMAIN,
    INPUT_NUMBER_MAX,
    INPUT_NUMBER_MIN,
    INPUT_NUMBER_STEP,
    PIN_TYPE_INPUT_NUMBER,
)

_LOGGER = logging.getLogger(__name__)


class BlynkNumber(BlynkEntity, NumberEntity):
    """Representation of a Blynk number input."""

    def __init__(self, coordinator, api, pin, config):
        """Initialize the number input."""
        super().__init__(coordinator, pin, config["pin_name"])
        self._api = api
        self._attr_native_min_value = config.get("min", INPUT_NUMBER_MIN)
        self._attr_native_max_value = config.get("max", INPUT_NUMBER_MAX)
        self._attr_native_step = config.get("step", INPUT_NUMBER_STEP)
        self._attr_mode = config.get("mode", "slider")

    @property
    def native_value(self):
        """Return the current value from coordinator cache.
        
        This reads directly from coordinator.data which is populated
        by the centralized polling mechanism. No API call is made here.
        """
        if not self.coordinator.data or self._pin not in self.coordinator.data:
            return None

        value = self.coordinator.data[self._pin]
        _LOGGER.debug("Number input %s value from cache: %s", self._pin, value)

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value with optimistic update.
        
        Write pattern that doesn't disrupt polling:
        1. Async write to API (non-blocking, uses write lock)
        2. Optimistically update coordinator cache for instant UI feedback
        3. Write state to Home Assistant
        4. Next scheduled coordinator refresh confirms actual device state
        
        No manual refresh requested - avoids disrupting the polling schedule.
        """
        try:
            _LOGGER.debug("Setting number input %s to %s", self._pin, value)
            
            # Async write to device (non-blocking, uses persistent session)
            success = await self._api.set_pin_value(self._pin, value)
            
            if success:
                # Optimistic cache update for instant UI response
                if self.coordinator.data:
                    self.coordinator.data[self._pin] = value
                self.async_write_ha_state()
            else:
                _LOGGER.warning("Failed to set number input %s to %s", self._pin, value)
        except Exception as err:
            _LOGGER.error("Error setting number value: %s", err)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Blynk number inputs based on config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    pins_config = entry.data.get("pins", {})

    entities = []
    for pin, config in pins_config.items():
        if config.get("pin_type") == PIN_TYPE_INPUT_NUMBER:
            entities.append(BlynkNumber(coordinator, api, pin, config))

    async_add_entities(entities)
