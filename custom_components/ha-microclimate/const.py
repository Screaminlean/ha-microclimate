"""Constants for the HA Microclimate integration."""
from datetime import timedelta
from typing import Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
)
from homeassistant.components.switch import (
    SwitchDeviceClass,
)

DOMAIN: Final = "ha_microclimate"
VERSION: Final = "0.0.3"
MANUFACTURER: Final = "Microclimate"

# Configuration
CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_DEVICE_NAME: Final = "device_name"
CONF_DEVICE_MODEL: Final = "device_model"
CONF_PIN_TYPE: Final = "pin_type"
CONF_PIN_NAME: Final = "pin_name"
CONF_DEVICE_CLASS: Final = "device_class"
CONF_UNIT: Final = "unit"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 120
DEFAULT_TIMEOUT: Final = 10
DEFAULT_DEVICE_NAME: Final = "Microclimate Device"
DEFAULT_DEVICE_MODEL: Final = "Blynk Connected Device"

# Supported Device Models
DEVICE_MODEL_EVO_CONNECTED_2: Final = "Evo Connected 2"
DEVICE_MODEL_EVO_LITE: Final = "Evo Lite"
DEVICE_MODEL_GENERIC: Final = "Generic Blynk Device"

SUPPORTED_MODELS: Final = {
    DEVICE_MODEL_EVO_CONNECTED_2: "Microclimate Evo Connected 2",
    DEVICE_MODEL_EVO_LITE: "Microclimate Evo Lite",
    DEVICE_MODEL_GENERIC: "Generic Device",
}

# API
API_URL: Final = "https://microclimate.blynk.cc/external/api"
API_HEADERS: Final = {"Content-Type": "application/json"}

# Pin Types
PIN_TYPE_SENSOR: Final = "sensor"
PIN_TYPE_BINARY_SENSOR: Final = "binary_sensor"
PIN_TYPE_SWITCH: Final = "switch"
PIN_TYPE_INPUT_NUMBER: Final = "input_number"
PIN_TYPE_BUTTON: Final = "button"
PIN_TYPE_INPUT_TEXT: Final = "input_text"
PIN_TYPE_SELECT: Final = "select"
PIN_TYPE_PACKED_TIME_TEXT: Final = "packed_time_text"

PIN_TYPE_OPTIONS: Final = {
    PIN_TYPE_SENSOR: "Sensor",
    PIN_TYPE_BINARY_SENSOR: "Binary Sensor",
    PIN_TYPE_SWITCH: "Switch",
    PIN_TYPE_INPUT_NUMBER: "Input Number",
    PIN_TYPE_BUTTON: "Button",
    PIN_TYPE_INPUT_TEXT: "Text Input",
    PIN_TYPE_SELECT: "Select",
    PIN_TYPE_PACKED_TIME_TEXT: "Packed Time Helper",
}

# Device Classes
SENSOR_DEVICE_CLASSES = {
    "none": None,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "power": SensorDeviceClass.POWER,
    "current": SensorDeviceClass.CURRENT,
    "voltage": SensorDeviceClass.VOLTAGE,
    "energy": SensorDeviceClass.ENERGY,
    "battery": SensorDeviceClass.BATTERY
}

BINARY_SENSOR_DEVICE_CLASSES = {
    "none": None,
    "motion": BinarySensorDeviceClass.MOTION,
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "light": BinarySensorDeviceClass.LIGHT
}

SWITCH_DEVICE_CLASSES = {
    "none": None,
    "switch": SwitchDeviceClass.SWITCH,
    "outlet": SwitchDeviceClass.OUTLET
}

COMMON_UNITS = {
    "none": None,
    "°C": "°C",
    "%": "%",
    "W": "W",
    "A": "A",
    "V": "V",
    "kWh": "kWh"
}

# Input Number Configuration
INPUT_NUMBER_MIN: Final = 0
INPUT_NUMBER_MAX: Final = 100
INPUT_NUMBER_STEP: Final = 1

# Input Text Configuration
INPUT_TEXT_MIN_LENGTH: Final = 0
INPUT_TEXT_MAX_LENGTH: Final = 100

# Integration Metadata
ATTRIBUTION: Final = "Data provided by Blynk Cloud via HA Microclimate"
INTEGRATION_CREATED: Final = "2026-05-28"
INTEGRATION_CREATOR: Final = "Screaminlean"

# Update coordinator parameters
SCAN_INTERVAL: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
REQUEST_TIMEOUT: Final = 10
