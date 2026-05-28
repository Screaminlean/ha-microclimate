"""Blynk Cloud API implementation with optimized write handling.

Write Architecture:
- Persistent aiohttp session for connection pooling
- Async write queue to prevent conflicts with polling
- Writes don't block or disrupt the main coordinator polling loop
- Proper session cleanup on shutdown
- Timeout and error handling for all operations
"""
import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any, List
import urllib.parse

from .const import API_URL, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

class BlynkCloudAPI:
    """Blynk Cloud API with optimized read/write handling.
    
    Features:
    - Persistent session for connection pooling
    - Batch reads for efficient polling
    - Async writes that don't block polling
    - Proper error handling and logging
    """
    
    def __init__(self, token: str):
        """Initialize the API.
        
        Args:
            token: Blynk device authentication token
        """
        self.token = token
        self.base_url = API_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._write_lock = asyncio.Lock()
        self._pending_writes: Dict[str, Any] = {}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists, creating if needed.
        
        Uses connection pooling for better performance.
        Session is reused across all API calls.
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session and cleanup resources.
        
        Should be called when integration is unloaded.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        _LOGGER.debug("API session closed")

    async def _make_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Make a request to the Blynk API using persistent session.
        
        Args:
            endpoint: API endpoint with parameters
            
        Returns:
            Parsed response data or None on error
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            session = await self._ensure_session()
            async with session.get(url) as response:
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

    async def get_pins_batch(self, pins: List[str]) -> Dict[str, Any]:
        """Get multiple pins in a single batch request.
        
        Args:
            pins: List of pin names to fetch (e.g., ['V0', 'V1', 'V2'])
            
        Returns:
            Dictionary mapping pin names to their values
        """
        if not pins:
            return {}
        
        # Normalize pin names
        normalized_pins = [pin.upper() for pin in pins]
        
        # Build query string for batch request: get?token={token}&v0&v1&v2
        pin_params = "&".join(normalized_pins)
        endpoint = f"get?token={self.token}&{pin_params}"
        
        _LOGGER.debug("Batch fetching pins: %s", normalized_pins)
        response = await self._make_request(endpoint)
        
        if not response:
            return {}
        
        processed_data = {}
        
        # The Blynk API returns the pins as keys in the response
        if isinstance(response, dict):
            for pin, value in response.items():
                if value is not None:
                    pin_name = pin.upper()
                    parsed_value = self._parse_value(value)
                    processed_data[pin_name] = parsed_value
        
        _LOGGER.debug("Batch processed %d/%d pins", len(processed_data), len(normalized_pins))
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
        """Set pin value asynchronously without blocking polling loop.
        
        This method is optimized for async writes:
        - Uses persistent session for connection pooling
        - Lock prevents concurrent write conflicts
        - Doesn't block coordinator polling
        - Tracks pending writes to handle rapid changes
        - Returns immediately with success/failure status
        
        Args:
            pin: Virtual pin identifier (e.g., 'V0')
            value: Value to set (bool, int, float, or string)
            
        Returns:
            True if write succeeded, False otherwise
        """
        # Normalize pin name
        pin = pin.upper()
        
        # Convert value to string for API
        if isinstance(value, bool):
            str_value = "1" if value else "0"
        elif isinstance(value, (int, float)):
            str_value = str(value)
        else:
            str_value = str(value)
        
        # Track pending write to avoid race conditions
        self._pending_writes[pin] = str_value
        
        # Use lock to prevent concurrent writes from interfering
        async with self._write_lock:
            try:
                # URL encode value for safe transmission
                encoded_value = urllib.parse.quote(str_value)
                url = f"{self.base_url}/update?token={self.token}&{pin}={encoded_value}"
                
                session = await self._ensure_session()
                
                # Perform async write without blocking
                async with session.get(url) as response:
                    _LOGGER.debug("Set pin %s to %s, status: %s", pin, str_value, response.status)
                    
                    if response.status == 200:
                        try:
                            result = await response.json()
                            _LOGGER.debug("Write successful for %s=%s, response: %s", pin, str_value, result)
                        except aiohttp.ContentTypeError:
                            text = await response.text()
                            _LOGGER.debug("Write successful for %s=%s, text: %s", pin, str_value, text)
                        
                        # Clear pending write on success
                        self._pending_writes.pop(pin, None)
                        return True
                    else:
                        error_text = await response.text()
                        _LOGGER.error("Failed to set %s=%s: HTTP %s - %s", pin, str_value, response.status, error_text)
                        self._pending_writes.pop(pin, None)
                        return False
                        
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout setting %s to %s", pin, str_value)
                self._pending_writes.pop(pin, None)
                return False
            except Exception as err:
                _LOGGER.error("Error setting %s to %s: %s", pin, str_value, str(err))
                self._pending_writes.pop(pin, None)
                return False

    def has_pending_write(self, pin: str) -> bool:
        """Check if a write is pending for a pin.
        
        Useful for avoiding race conditions during coordinator refresh.
        
        Args:
            pin: Virtual pin identifier
            
        Returns:
            True if write is in progress for this pin
        """
        return pin.upper() in self._pending_writes

    def get_pending_write_value(self, pin: str) -> Optional[Any]:
        """Get the pending write value for a pin.
        
        Used for optimistic updates during coordinator refresh.
        
        Args:
            pin: Virtual pin identifier
            
        Returns:
            Pending write value or None
        """
        return self._pending_writes.get(pin.upper())
