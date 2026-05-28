"""DataUpdateCoordinator for HA Microclimate.

This coordinator manages data fetching and device grouping for the integration:

Device Grouping Architecture:
- All virtual pins (V0, V1, V2...) belong to one physical device
- Uses Home Assistant's DeviceRegistry to group entities
- Creates a unified device dashboard in HA UI
- Device identified by (DOMAIN, entry_id) tuple
- Supports multiple device models (Evo Connected 2, Evo Lite, etc.)

Benefits:
- Clean, organized device view instead of scattered entities
- Single device card showing all sensors, switches, alarms
- Easy device-level automation triggers
- Professional appearance in Home Assistant UI
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .blynk_api import BlynkCloudAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class MicroclimateDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Microclimate data from Blynk Cloud API.
    
    This coordinator handles all data fetching for the integration:
    - Fetches all configured pins in a single batch request
    - Updates all entities simultaneously with fresh data
    - Manages polling interval and error handling centrally
    - Prevents individual entities from making redundant API calls
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: BlynkCloudAPI,
        token: str,
        configured_pins: list[str],
        scan_interval: int,
        device_name: str,
        device_model: str,
        entry_id: str,
    ) -> None:
        """Initialize the coordinator.
        
        Args:
            hass: Home Assistant instance
            api: Blynk Cloud API client
            token: Device authentication token
            configured_pins: List of pins configured by user
            scan_interval: Polling interval in seconds
            device_name: User-friendly device name
            device_model: Device model identifier
            entry_id: Config entry ID for unique device identification
        """
        self.api = api
        self.token = token
        self.configured_pins = configured_pins
        self.device_name = device_name
        self.device_model = device_model
        self.entry_id = entry_id
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{token[:8]}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Blynk Cloud API.
        
        This method is called automatically by Home Assistant at the configured
        interval. It fetches all configured pins in a single batch request for
        optimal performance.
        
        Returns:
            Dictionary mapping pin names to their current values
            
        Raises:
            UpdateFailed: If data cannot be fetched after multiple attempts
        """
        try:
            if self.configured_pins:
                # Use efficient batch mode for configured pins
                data = await self.api.get_pins_batch(self.configured_pins)
                _LOGGER.debug(
                    "Coordinator batch fetched %d pins for device %s",
                    len(self.configured_pins),
                    self.token[:8],
                )
            else:
                # Fallback to get all pins if no specific pins configured
                data = await self.api.get_all_pins()
                _LOGGER.debug(
                    "Coordinator fetched all pins for device %s",
                    self.token[:8],
                )
            
            if not data:
                self._consecutive_errors += 1
                if self._consecutive_errors >= self._max_consecutive_errors:
                    _LOGGER.error(
                        "No data received after %d consecutive attempts",
                        self._consecutive_errors,
                    )
                raise UpdateFailed("No data received from device")
            
            # Reset error counter on success
            if self._consecutive_errors > 0:
                _LOGGER.info(
                    "Connection restored for device %s after %d failed attempts",
                    self.token[:8],
                    self._consecutive_errors,
                )
                self._consecutive_errors = 0
            
            return data
            
        except UpdateFailed:
            raise
        except Exception as err:
            self._consecutive_errors += 1
            _LOGGER.error(
                "Error fetching data for device %s (attempt %d/%d): %s",
                self.token[:8],
                self._consecutive_errors,
                self._max_consecutive_errors,
                err,
            )
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def update_configured_pins(self, pins: list[str]) -> None:
        """Update the list of configured pins.
        
        This can be called if the configuration changes at runtime.
        
        Args:
            pins: New list of pin names to fetch
        """
        self.configured_pins = pins
        _LOGGER.debug(
            "Coordinator pin configuration updated: %d pins for device %s",
            len(pins),
            self.token[:8],
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for entities.
        
        All entities belonging to this physical device will be grouped
        together in Home Assistant's Device Registry using this info.
        This creates a clean, unified device dashboard showing all pins.
        """
        from .const import MANUFACTURER, VERSION
        
        return {
            "identifiers": {(DOMAIN, self.entry_id)},
            "name": self.device_name,
            "manufacturer": MANUFACTURER,
            "model": self.device_model,
            "sw_version": VERSION,
            "configuration_url": "https://microclimate.blynk.cc/",
        }

    @property
    def is_healthy(self) -> bool:
        """Return True if coordinator is in healthy state."""
        return self._consecutive_errors < self._max_consecutive_errors
