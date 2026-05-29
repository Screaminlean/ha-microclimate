"""Support for Blynk sensors.

Sensor entities demonstrate the coordinator pattern for read-only entities:
- All state reads come from coordinator.data
- No direct API calls are made by sensor entities
- Data is automatically refreshed by the coordinator at the configured interval
- Multiple sensors update simultaneously from a single batch API request
"""

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlynkEntity
from .const import (
    COMMON_UNITS,
    CONF_DEVICE_CLASS,
    CONF_ENABLED_BY_DEFAULT,
    CONF_UNIT,
    DOMAIN,
    PIN_TYPE_SENSOR,
    SENSOR_DEVICE_CLASSES,
)

_LOGGER = logging.getLogger(__name__)


class BlynkSensor(BlynkEntity, SensorEntity):
    """Representation of a Blynk sensor."""

    def __init__(self, coordinator, pin, config):
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            pin,
            config["pin_name"],
            enabled_by_default=config.get(CONF_ENABLED_BY_DEFAULT, True),
        )

        device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_device_class = SENSOR_DEVICE_CLASSES.get(device_class)
        self._attr_native_unit_of_measurement = COMMON_UNITS.get(config.get(CONF_UNIT))

    def _parse_value(self, value):
        """Parse value from Blynk, handling different formats."""
        if value is None:
            return None

        _LOGGER.debug("Raw value from Blynk for pin %s: %s (type: %s)", self._pin, value, type(value))

        if isinstance(value, (int, float)):
            return value

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None

            try:
                if "," in value and "." not in value:
                    value = value.replace(",", ".")
                elif "," in value and "." in value:
                    last_dot = value.rfind(".")
                    if "," in value[:last_dot]:
                        value = value.replace(",", "")

                return float(value)
            except ValueError:
                return value

        return value

    @property
    def native_value(self):
        """Return the state of the sensor from coordinator cache.
        
        This reads directly from coordinator.data which is populated
        by the centralized polling mechanism. No API call is made here.
        Sensors are purely read-only and never make individual requests.
        """
        if not self.coordinator.data or self._pin not in self.coordinator.data:
            return None

        raw_value = self.coordinator.data[self._pin]
        parsed_value = self._parse_value(raw_value)
        _LOGGER.debug("Pin %s - Raw from cache: %s, Parsed: %s", self._pin, raw_value, parsed_value)
        return parsed_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Blynk sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []

    for pin, pin_config in entry.data["pins"].items():
        if pin_config["pin_type"] == PIN_TYPE_SENSOR:
            entities.append(BlynkSensor(coordinator, pin, pin_config))

    async_add_entities(entities)
