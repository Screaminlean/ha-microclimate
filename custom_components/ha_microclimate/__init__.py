"""The HA Microclimate integration.

This integration uses a centralized DataUpdateCoordinator pattern to efficiently
manage data fetching from the Blynk Cloud API and groups all entities under a
single physical device in Home Assistant's Device Registry.

Architecture:
1. MicroclimateDataUpdateCoordinator - Central polling manager
   - Fetches all configured pins in a single batch HTTP request
   - Runs on a configurable polling interval (default: 120s)
   - Manages error handling and connection health tracking
   - Distributes data to all entities simultaneously
   - Provides unified device_info for entity grouping

2. Device Grouping
   - All virtual pins belong to one physical device
   - Unified device dashboard in Home Assistant UI
   - Device identified by (DOMAIN, entry_id)
   - Supports multiple device models (Evo Connected 2, Evo Lite, etc.)
   - Clean, professional appearance with all sensors/switches grouped

3. BlynkEntity - Base class for all entity types
   - Inherits from CoordinatorEntity for automatic updates
   - Reads state from coordinator.data (no individual API calls)
   - Uses coordinator.device_info for proper device grouping
   - Uses coordinator for availability checking

4. Platform Entities - Sensor, Switch, Number, etc.
   - Inherit from BlynkEntity
   - Read-only entities (sensor, binary_sensor) only read from coordinator
   - Writable entities (switch, number, etc.) use API for commands, coordinator for state

Benefits:
- Single HTTP request per polling interval (instead of N requests)
- All entities update simultaneously with consistent data
- Reduced API load and network overhead
- Better error handling and recovery
- Optimal performance for devices with many pins
- Clean, unified device view in Home Assistant UI
- Easy device-level automations and management
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .blynk_api import BlynkCloudAPI
from .coordinator import MicroclimateDataUpdateCoordinator
from .const import (
    ATTRIBUTION,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
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

    # Initial connection test to verify token and connectivity
    try:
        initial_data = await api.get_all_pins()
        if not initial_data:
            _LOGGER.error("No data received from Blynk API")
            raise ConfigEntryNotReady("No data received from device")
        _LOGGER.info("Initial data received: %s", initial_data)
    except Exception as err:
        _LOGGER.error("Error setting up integration: %s", err)
        raise ConfigEntryNotReady from err

    # Extract configured pins for efficient batch fetching
    configured_pins = list(entry.data.get("pins", {}).keys())
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    device_name = entry.data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)
    device_model = entry.data.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL)

    # Create the centralized data coordinator with device grouping
    coordinator = MicroclimateDataUpdateCoordinator(
        hass=hass,
        api=api,
        token=entry.data[CONF_TOKEN],
        configured_pins=configured_pins,
        scan_interval=scan_interval,
        device_name=device_name,
        device_model=device_model,
        entry_id=entry.entry_id,
    )

    # Set initial data to avoid waiting for first refresh
    coordinator.data = initial_data

    # Store coordinator and API for entity platforms
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    # Forward setup to all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Start the coordinator's background polling
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info(
        "Successfully set up %s (%s) with %d configured pins",
        device_name,
        device_model,
        len(configured_pins),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and cleanup resources."""
    # Stop the coordinator and cleanup
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Cleanup API session
        await api.close()
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        _LOGGER.info(
            "Successfully unloaded %s (%s)",
            coordinator.device_name,
            coordinator.device_model,
        )
    
    return unload_ok


class BlynkEntity(CoordinatorEntity):
    """Represents a Blynk entity.
    
    All entity types inherit from this base class to ensure consistent
    behavior and proper coordinator integration. Entities automatically
    receive updates when the coordinator fetches new data.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MicroclimateDataUpdateCoordinator,
        pin: str,
        name: str,
        enabled_by_default: bool = True,
    ) -> None:
        """Initialize the entity.
        
        Args:
            coordinator: The data update coordinator
            pin: Virtual pin identifier (e.g., 'V0')
            name: Friendly name for the entity
        """
        super().__init__(coordinator)

        # Normalize pin name
        if not pin.startswith("V"):
            self._pin = "V" + pin
        elif pin.startswith("VV"):
            self._pin = "V" + pin[2:]
        else:
            self._pin = pin

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{coordinator.entry_id}_{self._pin}"
        self._attr_entity_registry_enabled_default = enabled_by_default
        self._attr_device_info = coordinator.device_info
        self._attr_attribution = ATTRIBUTION

    @property
    def available(self) -> bool:
        """Return True if entity is available.
        
        Entity is available if:
        - Coordinator successfully communicated with API
        - Data was received
        - This entity's pin is in the received data
        """
        return bool(
            self.coordinator.last_update_success
            and self.coordinator.data
            and self._pin in self.coordinator.data
        )
