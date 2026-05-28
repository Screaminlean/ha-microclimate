"""The HA Microclimate integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .blynk_api import BlynkCloudAPI
from .const import (
    ATTRIBUTION,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.TEXT,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Microclimate from a config entry."""
    api = BlynkCloudAPI(entry.data[CONF_TOKEN])

    try:
        initial_data = await api.get_all_pins()
        if not initial_data:
            _LOGGER.error("No data received from Blynk API")
            raise ConfigEntryNotReady("No data received from device")
        _LOGGER.info("Initial data received: %s", initial_data)
    except Exception as err:
        _LOGGER.error("Error setting up integration: %s", err)
        raise ConfigEntryNotReady from err

    coordinator: DataUpdateCoordinator

    async def async_update_data() -> dict[str, Any]:
        """Fetch data from API."""
        try:
            data = await api.get_all_pins()
            _LOGGER.debug(
                "Received data from Blynk device %s: %s",
                entry.data[CONF_TOKEN][:8],
                data,
            )
            if not data:
                raise UpdateFailed("No data received")
            return data
        except Exception as err:
            _LOGGER.error("Error communicating with Blynk API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}")

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.data[CONF_TOKEN][:8]}",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    coordinator.data = initial_data

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class BlynkEntity(CoordinatorEntity):
    """Represents a Blynk entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        pin: str,
        name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        if not pin.startswith("V"):
            self._pin = "V" + pin
        elif pin.startswith("VV"):
            self._pin = "V" + pin[2:]
        else:
            self._pin = pin

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{self._pin}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.name)},
            "name": f"HA Microclimate ({coordinator.name})",
            "manufacturer": MANUFACTURER,
            "model": "Cloud Device",
            "sw_version": VERSION,
        }

        self._attr_attribution = ATTRIBUTION

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(
            self.coordinator.last_update_success
            and self.coordinator.data
            and self._pin in self.coordinator.data
        )
