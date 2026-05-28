"""Config flow for HA Microclimate."""

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .blynk_api import BlynkCloudAPI
from .const import (
    BINARY_SENSOR_DEVICE_CLASSES,
    COMMON_UNITS,
    CONF_DEVICE_CLASS,
    CONF_PIN_NAME,
    CONF_PIN_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INPUT_NUMBER_MAX,
    INPUT_NUMBER_MIN,
    INPUT_NUMBER_STEP,
    INPUT_TEXT_MAX_LENGTH,
    INPUT_TEXT_MIN_LENGTH,
    PIN_TYPE_BINARY_SENSOR,
    PIN_TYPE_BUTTON,
    PIN_TYPE_INPUT_NUMBER,
    PIN_TYPE_INPUT_TEXT,
    PIN_TYPE_PACKED_TIME_TEXT,
    PIN_TYPE_OPTIONS,
    PIN_TYPE_SELECT,
    PIN_TYPE_SENSOR,
    PIN_TYPE_SWITCH,
    SENSOR_DEVICE_CLASSES,
    SWITCH_DEVICE_CLASSES,
)
from .pin_map_loader import get_default_pin_type, get_pin_defaults

_LOGGER = logging.getLogger(__name__)


class BlynkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Microclimate."""

    VERSION = 12

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._token = None
        self._scan_interval = DEFAULT_SCAN_INTERVAL
        self._discovered_pins = []
        self._pin_values = {}
        self._pin_selection = []
        self._pin_types = {}
        self._pin_defaults = {}
        self._pin_configs = {}
        self._pin_config_order = []
        self._current_pin_index = 0
        self._api = None

    async def async_step_user(self, user_input=None):
        """Step 1: Token entry."""
        errors = {}
        if user_input is not None:
            self._token = user_input[CONF_TOKEN].strip()

            if len(self._token) < 10:
                errors["base"] = "invalid_token_format"
            else:
                for entry in self._async_current_entries():
                    if entry.data.get(CONF_TOKEN) == self._token:
                        return self.async_abort(reason="already_configured")

                self._api = BlynkCloudAPI(self._token)
                return await self.async_step_http_config()

        schema = {
            vol.Required(CONF_TOKEN): str,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_http_config(self, user_input=None):
        """Step 2: HTTP polling configuration."""
        errors = {}
        if user_input is not None:
            self._scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            if not (10 <= self._scan_interval <= 3600):
                errors["base"] = "invalid_scan_interval"
            else:
                return await self.async_step_connection()

        schema = {
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=3600,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="seconds",
                ),
            ),
        }

        return self.async_show_form(
            step_id="http_config",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_connection(self, user_input=None):
        """Step 3: Discover pins via HTTP."""
        errors = {}

        try:
            pins = await self._api.get_all_pins()
            if pins:
                self._discovered_pins = []
                self._pin_values = {}
                for pin, value in pins.items():
                    pin_name = pin.upper()
                    self._discovered_pins.append(pin_name)
                    self._pin_values[pin_name] = value
                    self._pin_defaults[pin_name] = get_pin_defaults(pin_name)
                    _LOGGER.info("Pin %s current value: %s", pin_name, value)

                return await self.async_step_pin_selection()

            errors["base"] = "no_pins_found"
        except Exception as err:
            _LOGGER.error("Error during connection test: %s", err)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="connection",
            errors=errors,
        )

    async def async_step_pin_selection(self, user_input=None):
        """Step 4: Select pins to configure."""
        errors = {}

        if user_input is not None:
            self._pin_selection = []
            self._pin_types = {}

            for pin in self._discovered_pins:
                enable_key = f"enable_{pin}"
                type_key = f"type_{pin}"

                if user_input.get(enable_key, False):
                    self._pin_selection.append(pin)
                    self._pin_types[pin] = user_input.get(type_key, PIN_TYPE_SENSOR)

            if not self._pin_selection:
                errors["base"] = "no_pins_selected"
            else:
                self._pin_config_order = self._pin_selection.copy()
                self._current_pin_index = 0
                return await self.async_step_pin_config()

        schema = {}
        for pin in sorted(self._discovered_pins):
            default_type = get_default_pin_type(pin)
            schema[vol.Optional(f"enable_{pin}", default=False)] = selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            )
            schema[vol.Optional(f"type_{pin}", default=default_type)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": v} for k, v in PIN_TYPE_OPTIONS.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="pin_selection",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_pin_config(self, user_input=None):
        """Step 5: Configure individual pins."""
        errors = {}

        if user_input is not None:
            prev_pin = self._pin_config_order[self._current_pin_index - 1]

            conf = {
                CONF_PIN_TYPE: self._pin_types[prev_pin],
                CONF_PIN_NAME: user_input[CONF_PIN_NAME],
            }
            if CONF_DEVICE_CLASS in user_input:
                conf[CONF_DEVICE_CLASS] = user_input[CONF_DEVICE_CLASS]
            if CONF_UNIT in user_input:
                conf[CONF_UNIT] = user_input[CONF_UNIT]

            if self._pin_types[prev_pin] == PIN_TYPE_INPUT_NUMBER:
                conf.update(
                    {
                        "min": user_input.get("min", INPUT_NUMBER_MIN),
                        "max": user_input.get("max", INPUT_NUMBER_MAX),
                        "step": user_input.get("step", INPUT_NUMBER_STEP),
                        "mode": user_input.get("mode", "slider"),
                    }
                )
            elif self._pin_types[prev_pin] == PIN_TYPE_INPUT_TEXT:
                conf.update(
                    {
                        "min_length": user_input.get("min_length", INPUT_TEXT_MIN_LENGTH),
                        "max_length": user_input.get("max_length", INPUT_TEXT_MAX_LENGTH),
                        "pattern": user_input.get("pattern"),
                    }
                )
            elif self._pin_types[prev_pin] == PIN_TYPE_SELECT:
                options_raw = user_input.get("select_options", "")
                values_raw = user_input.get("select_values", "")
                options = [item.strip() for item in options_raw.split(",") if item.strip()]
                values = [item.strip() for item in values_raw.split(",") if item.strip()]
                if options and values and len(options) == len(values):
                    conf.update(
                        {
                            "select_options": options,
                            "select_values": values,
                        }
                    )

            self._pin_configs[prev_pin] = conf

        if self._current_pin_index >= len(self._pin_config_order):
            config_data = {
                CONF_TOKEN: self._token,
                CONF_SCAN_INTERVAL: self._scan_interval,
                "pins": self._pin_configs,
            }

            return self.async_create_entry(
                title=f"HA Microclimate ({self._token[:8]}...) - HTTP",
                data=config_data,
            )

        pin = self._pin_config_order[self._current_pin_index]
        pin_type = self._pin_types[pin]
        pin_defaults = self._pin_defaults.get(pin, {})

        default_name = str(pin_defaults.get("description") or pin)

        schema = {
            vol.Required(CONF_PIN_NAME, default=default_name): str,
        }

        if pin_type == PIN_TYPE_SENSOR:
            schema[vol.Optional(CONF_DEVICE_CLASS, default="none")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": k} for k in SENSOR_DEVICE_CLASSES.keys()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            )
            schema[vol.Optional(CONF_UNIT, default="none")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": k} for k in COMMON_UNITS.keys()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            )
        elif pin_type == PIN_TYPE_BINARY_SENSOR:
            schema[vol.Optional(CONF_DEVICE_CLASS, default="none")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": k} for k in BINARY_SENSOR_DEVICE_CLASSES.keys()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            )
        elif pin_type == PIN_TYPE_SWITCH:
            schema[vol.Optional(CONF_DEVICE_CLASS, default="none")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": k} for k in SWITCH_DEVICE_CLASSES.keys()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            )
        elif pin_type == PIN_TYPE_INPUT_NUMBER:
            schema.update(
                {
                    vol.Optional("min", default=INPUT_NUMBER_MIN): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=-1000000,
                            max=1000000,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("max", default=INPUT_NUMBER_MAX): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=-1000000,
                            max=1000000,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("step", default=INPUT_NUMBER_STEP): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.001,
                            max=1000,
                            step=0.001,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("mode", default="slider"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "slider", "label": "Slider"},
                                {"value": "box", "label": "Box"},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            )
        elif pin_type == PIN_TYPE_INPUT_TEXT:
            schema.update(
                {
                    vol.Optional("min_length", default=INPUT_TEXT_MIN_LENGTH): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=255,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("max_length", default=INPUT_TEXT_MAX_LENGTH): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=255,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("pattern"): str,
                }
            )
        elif pin_type == PIN_TYPE_SELECT:
            known_mapping = pin_defaults.get("select_options", {})
            default_values = ", ".join(known_mapping.keys())
            default_options = ", ".join(known_mapping.values())
            schema.update(
                {
                    vol.Optional("select_values", default=default_values): str,
                    vol.Optional("select_options", default=default_options): str,
                }
            )
        elif pin_type == PIN_TYPE_PACKED_TIME_TEXT:
            schema.update(
                {
                    vol.Optional("min_length", default=INPUT_TEXT_MIN_LENGTH): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=255,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional("max_length", default=INPUT_TEXT_MAX_LENGTH): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=255,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                }
            )

        self._current_pin_index += 1

        return self.async_show_form(
            step_id="pin_config",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "pin_number": pin,
                "current_value": str(self._pin_values.get(pin, "N/A")),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ClimateConnectBridgeOptionsFlowHandler(config_entry)


class ClimateConnectBridgeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle HA Microclimate options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self.options = dict(config_entry.options)
        if not self.options:
            self.options = {
                CONF_SCAN_INTERVAL: config_entry.data.get(
                    CONF_SCAN_INTERVAL,
                    DEFAULT_SCAN_INTERVAL,
                )
            }

    async def async_step_init(self, user_input=None):
        """Manage integration options."""
        errors = {}

        if user_input is not None:
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if not (10 <= scan_interval <= 3600):
                errors["base"] = "invalid_scan_interval"
            else:
                new_data = dict(self._config_entry.data)
                new_data[CONF_SCAN_INTERVAL] = scan_interval
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=new_data,
                )
                return self.async_create_entry(
                    title="",
                    data={CONF_SCAN_INTERVAL: scan_interval},
                )

        schema = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=3600,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="seconds",
                ),
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
