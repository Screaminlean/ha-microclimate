"""Support for Blynk button with visual feedback."""

import asyncio
import logging
from datetime import datetime

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlynkEntity
from .const import CONF_PIN_NAME, CONF_PIN_TYPE, DOMAIN, PIN_TYPE_BUTTON

_LOGGER = logging.getLogger(__name__)


class BlynkButton(BlynkEntity, ButtonEntity):
    """Representation of a Blynk button with visual press feedback."""

    def __init__(self, coordinator, api, pin, config):
        """Initialize the button."""
        super().__init__(coordinator, pin, config[CONF_PIN_NAME])
        self._api = api
        self._attr_name = config[CONF_PIN_NAME]
        self._attr_unique_id = f"{DOMAIN}_{self._pin}_button"

        self._is_visually_pressed = False
        self._reset_timer = None
        self._last_press_time = None

        self._normal_icon = "mdi:gesture-tap"
        self._pressed_icon = "mdi:gesture-tap-button"
        self._attr_icon = self._normal_icon

        self._attr_extra_state_attributes = {
            "pin": self._pin,
            "last_pressed": None,
            "press_count": 0,
        }

    async def _show_visual_press(self):
        """Show visual feedback when button is pressed."""
        if self._reset_timer:
            self._reset_timer.cancel()

        self._is_visually_pressed = True
        self._attr_icon = self._pressed_icon
        self._last_press_time = datetime.now()
        self._attr_extra_state_attributes["last_pressed"] = self._last_press_time.isoformat()
        self._attr_extra_state_attributes["press_count"] = self._attr_extra_state_attributes.get("press_count", 0) + 1

        self.async_write_ha_state()
        self._reset_timer = asyncio.create_task(self._reset_visual_state())

    async def _reset_visual_state(self):
        """Reset visual state after delay."""
        await asyncio.sleep(1)
        self._is_visually_pressed = False
        self._attr_icon = self._normal_icon
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Handle the button press from Home Assistant."""
        try:
            _LOGGER.info("Button pressed from HA: %s", self.name)

            await self._show_visual_press()
            await self._api.set_pin_value(self._pin, "1")
            await asyncio.sleep(0.1)
            await self._api.set_pin_value(self._pin, "0")
        except Exception as err:
            _LOGGER.error("Error pressing button: %s", err)
            if self._is_visually_pressed:
                await self._reset_visual_state()

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        return self._attr_extra_state_attributes

    async def async_will_remove_from_hass(self):
        """Clean up when removing from Home Assistant."""
        if self._reset_timer:
            self._reset_timer.cancel()
        await super().async_will_remove_from_hass()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Blynk button entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    pins_config = entry.data.get("pins", {})

    entities = []
    for pin, config in pins_config.items():
        pin_type = config.get(CONF_PIN_TYPE)
        if pin_type == PIN_TYPE_BUTTON:
            button = BlynkButton(coordinator, api, pin, config)
            entities.append(button)

    if entities:
        async_add_entities(entities, update_before_add=True)
