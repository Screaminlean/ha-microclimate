"""Support for Blynk binary sensors.

Binary sensor entities are read-only and demonstrate optimal coordinator usage:
- State reads ONLY from coordinator.data (cached, no API calls)
- No individual polling or API requests
- Automatic updates when coordinator refreshes every scan_interval
- Entity availability tied to coordinator success
"""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlynkEntity
from .const import (
    BINARY_SENSOR_DEVICE_CLASSES,
    CONF_DEVICE_CLASS,
    CONF_ENABLED_BY_DEFAULT,
    DOMAIN,
    PIN_TYPE_BINARY_SENSOR,
)

_LOGGER = logging.getLogger(__name__)


class BlynkBinarySensor(BlynkEntity, BinarySensorEntity):
    """Representation of a Blynk binary sensor."""

    def __init__(self, coordinator, pin, config):
        """Initialize the binary sensor."""
        super().__init__(
            coordinator,
            pin,
            config["pin_name"],
            enabled_by_default=config.get(CONF_ENABLED_BY_DEFAULT, True),
        )

        device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_device_class = BINARY_SENSOR_DEVICE_CLASSES.get(device_class)

    @property
    def is_on(self):
        """Return true if the binary sensor is on, reading from coordinator cache.
        
        This reads directly from coordinator.data which is populated
        by the centralized polling mechanism. No API call is made here.
        Binary sensors are purely read-only and never make individual requests.
        """
        if not self.coordinator.data or self._pin not in self.coordinator.data:
            return None

        value = self.coordinator.data[self._pin]
        _LOGGER.debug("Binary sensor %s value from cache: %s (type: %s)", self._pin, value, type(value))

        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "on", "yes")
        return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Blynk binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []

    for pin, pin_config in entry.data["pins"].items():
        if pin_config["pin_type"] == PIN_TYPE_BINARY_SENSOR:
            entities.append(BlynkBinarySensor(coordinator, pin, pin_config))

    async_add_entities(entities)
