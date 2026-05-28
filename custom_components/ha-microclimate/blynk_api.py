"""Blynk Cloud API implementation."""
import aiohttp
import logging
from typing import Optional, Dict, Any

from .const import API_URL, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

class BlynkCloudAPI:
    """Blynk Cloud API."""
    
    def __init__(self, token: str):
        """Initialize the API."""
        self.token = token
        self.base_url = API_URL

    async def _make_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Make a request to the Blynk API."""
        url = f"{self.base_url}/{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=DEFAULT_TIMEOUT) as response:
                    _LOGGER.debug("API request to %s, status: %s", url, response.status)
                    if response.status == 200:
                        try:
                            return await response.json()
                        except aiohttp.ContentTypeError:
                            text = await response.text()
                            # Blynk API sometimes returns plain text
                            if text:
                                try:
                                    # Check whether the value is numeric
                                    float_val = float(text)
                                    if float_val.is_integer():
                                        return {"value": int(float_val)}
                                    return {"value": float_val}
                                except ValueError:
                                    return {"value": text}
                            return None
                    else:
                        _LOGGER.error("API request failed: %s - %s", response.status, await response.text())
                        return None
        except asyncio.TimeoutError:
            _LOGGER.error("API request timeout to %s", url)
            return None
        except Exception as err:
            _LOGGER.error("API request error to %s: %s", url, str(err))
            return None

    def _parse_value(self, value):
        """Parse value from API response."""
        if value is None:
            return None
        
        # If it is a string
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            
            # Check whether it is numeric
            try:
                # First convert comma to dot (for locale-specific decimal format)
                if ',' in value and '.' not in value:
                    value = value.replace(',', '.')
                
                # Check thousands separator usage (e.g. 1,234.56)
                if ',' in value and '.' in value:
                    # If there is a comma before the final dot, treat it as thousands separator
                    last_dot = value.rfind('.')
                    if ',' in value[:last_dot]:
                        # Remove commas (thousands separators)
                        value = value.replace(',', '')
                
                # Convert to float
                parsed = float(value)
                # Convert to int when the float is a whole number
                if parsed.is_integer():
                    return int(parsed)
                return parsed
            except ValueError:
                # If not numeric, return as string
                return value
        
        # If already numeric
        if isinstance(value, (int, float)):
            return value
        
        # If boolean
        if isinstance(value, bool):
            return value
        
        # Convert other types to string
        return str(value)

    async def get_all_pins(self) -> Dict[str, Any]:
        """Get all pins from the device."""
        response = await self._make_request(f"getAll?token={self.token}")
        if not response:
            return {}
        
        processed_data = {}
        for pin, value in response.items():
            if value is not None:
                # Normalize pin names (V0, V1, etc.)
                pin_name = pin.upper()
                # Parse values
                parsed_value = self._parse_value(value)
                processed_data[pin_name] = parsed_value
        
        _LOGGER.debug("Processed pin data: %s", processed_data)
        return processed_data

    async def get_pin_value(self, pin: str) -> Optional[Any]:
        """Get value of a specific pin."""
        # Normalize pin name
        pin = pin.upper()
        response = await self._make_request(f"get?token={self.token}&{pin}")
        
        if response:
            # Parse API response
            if isinstance(response, dict):
                # Blynk API sometimes returns {"V0": "value"}
                for key, value in response.items():
                    if key.upper() == pin:
                        return self._parse_value(value)
                # Or it may return {"value": "value"}
                if "value" in response:
                    return self._parse_value(response["value"])
            else:
                # Direct value
                return self._parse_value(response)
        
        _LOGGER.debug("No value found for pin %s", pin)
        return None

    async def set_pin_value(self, pin: str, value: Any) -> bool:
        """Set pin value."""
        # Normalize pin name
        pin = pin.upper()
        
        # Convert value to string
        if isinstance(value, bool):
            str_value = "1" if value else "0"
        elif isinstance(value, (int, float)):
            str_value = str(value)
        else:
            str_value = str(value)
        
        # URL encoding may be required for Blynk API
        import urllib.parse
        encoded_value = urllib.parse.quote(str_value)
        
        url = f"{self.base_url}/update?token={self.token}&{pin}={encoded_value}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=DEFAULT_TIMEOUT) as response:
                    _LOGGER.debug("Set pin request to %s, status: %s", url, response.status)
                    if response.status == 200:
                        try:
                            result = await response.json()
                            _LOGGER.debug("Set pin %s to %s successful, response: %s", pin, str_value, result)
                            return True
                        except aiohttp.ContentTypeError:
                            text = await response.text()
                            if text and "OK" in text.upper():
                                _LOGGER.debug("Set pin %s to %s successful", pin, str_value)
                                return True
                            _LOGGER.debug("Set pin response text: %s", text)
                            return True  # Blynk sometimes returns only OK
                    else:
                        _LOGGER.error("Failed to set pin %s to %s: %s", pin, str_value, response.status)
                        return False
        except Exception as err:
            _LOGGER.error("Error setting pin %s to %s: %s", pin, str_value, str(err))
            return False
