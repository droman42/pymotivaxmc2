"""
Emotiva A/V Receiver Control Module

This module provides a Python interface for controlling Emotiva A/V receivers over the network.
It implements the Emotiva UDP protocol for device discovery, command sending, and event notification.
"""

import socket
import time
import logging
import asyncio
from typing import Optional, Dict, Any, Callable, List, Tuple, Set
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

from .exceptions import (
    InvalidTransponderResponseError,
    InvalidSourceError,
    InvalidModeError,
    DeviceOfflineError
)
from .utils import format_request, parse_response, validate_response, extract_command_response
from .constants import (
    DISCOVER_REQ_PORT, DISCOVER_RESP_PORT, NOTIFY_EVENTS,
    PROTOCOL_VERSION, DEFAULT_KEEPALIVE_INTERVAL,
    MODE_PRESETS, INPUT_SOURCES
)
from .network import AsyncSocketManager
from .notifier import AsyncEmotivaNotifier
from .types import EmotivaConfig

_LOGGER = logging.getLogger(__name__)

class Emotiva:
    """
    Main class for controlling Emotiva A/V receivers.
    
    This class provides methods for:
    - Device discovery
    - Sending commands
    - Receiving notifications
    - Managing device state
    
    Attributes:
        _ip (str): IP address of the Emotiva device
        _timeout (int): Socket timeout in seconds
        _transponder_port (Optional[int]): Port for command communication
        _callback (Optional[Callable]): Function to handle device notifications
        _lock (asyncio.Lock): Lock for thread-safe operations
        _config (EmotivaConfig): Configuration object
        _last_keepalive (datetime): Timestamp of last keepalive received
        _missed_keepalives (int): Number of missed keepalives
        _sequence_number (int): Current sequence number for notifications
        _notifier (AsyncEmotivaNotifier): Handles notification reception
        _subscribed_events (Set[str]): Set of events already subscribed to
    """
    
    def __init__(self, config: EmotivaConfig) -> None:
        """
        Initialize the Emotiva controller.
        
        Args:
            config: Configuration object with device settings
        """
        self._ip = config.ip
        self._config = config
        self._timeout = config.timeout
        self._transponder_port = None
        self._callback = None
        self._discovery_complete = False
        
        # Create the asyncio notifier for handling notifications
        self._notifier = AsyncEmotivaNotifier()
        self._notification_registered = False
        
        # Keepalive status tracking
        self._last_keepalive = time.time()
        self._missed_keepalives = 0
        self._sequence_number = 0
        
        # Create asyncio lock for thread safety
        self._lock = asyncio.Lock()
        
        # Track which notification types we've subscribed to
        self._subscribed_events = set()
        
        _LOGGER.debug("Initialized with ip: %s, timeout: %d", self._ip, self._timeout)

    async def discover(self, timeout: float = 1.0) -> Dict[str, Any]:
        """
        Discover Emotiva device on the network asynchronously.
        
        Args:
            timeout: Timeout in seconds to wait for device response.
            
        Returns:
            Dictionary with discovery results.
        """
        # Set a specified timeout for discovery
        self._timeout = timeout
        discovery_result = {"status": "error", "message": "Discovery failed for unknown reason"}
        
        _LOGGER.debug("Starting discovery for %s", self._ip)
        
        # Create a socket for receiving the response
        response_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        response_sock.settimeout(timeout)
        
        try:
            # Bind to the response port
            try:
                response_sock.bind(('', self._config.discover_response_port))
                _LOGGER.debug("Bound to response port %d", self._config.discover_response_port)
            except OSError as e:
                # If we can't bind to the preferred port, use any available port
                response_sock.bind(('', 0))
                bound_port = response_sock.getsockname()[1]
                _LOGGER.debug("Could not bind to port %d: %s, using port %d instead", 
                             self._config.discover_response_port, e, bound_port)

            # Format ping request with protocol version 3.0 which is known to work
            discovery_request = format_request('emotivaPing', {'protocol': PROTOCOL_VERSION})
            _LOGGER.debug("Discovery request: %s", discovery_request)
            
            # Create a socket for sending the discovery request
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # If IP is known, send directly, otherwise broadcast
            if self._ip:
                # Try default port first
                send_sock.sendto(discovery_request, (self._ip, self._config.discover_request_port))
                _LOGGER.debug("Sent discovery request to %s:%d", self._ip, self._config.discover_request_port)
            else:
                # Broadcast to find device
                send_sock.sendto(discovery_request, ('<broadcast>', self._config.discover_request_port))
                _LOGGER.debug("Broadcast discovery request to port %d", self._config.discover_request_port)
            
            send_sock.close()
            
            # Wait for response using asyncio
            # Create a Future object for the response
            loop = asyncio.get_running_loop()
            response_future = loop.create_future()
            
            def socket_callback():
                try:
                    data, addr = response_sock.recvfrom(4096)
                    if not response_future.done():
                        response_future.set_result((data, addr))
                except Exception as e:
                    if not response_future.done():
                        response_future.set_exception(e)
            
            # Add socket to event loop
            loop.add_reader(response_sock.fileno(), socket_callback)
            
            try:
                # Wait for response with timeout
                data, addr = await asyncio.wait_for(response_future, timeout)
                _LOGGER.debug("Received discovery response from %s:%d: %s", 
                             addr[0], addr[1], data.decode('utf-8', errors='replace'))
                
                # Save the device IP and port
                self._ip = addr[0]
                self._transponder_port = addr[1]
                self._discovery_complete = True
                
                # Parse the response
                try:
                    doc = parse_response(data)
                    if doc is not None:
                        root_tag = doc.tag
                        _LOGGER.debug("Discovery response root tag: %s", root_tag)
                        
                        # Extract device info
                        if root_tag == 'emotivaTransponder':
                            # Get the model and version information
                            discovery_result = {
                                'model': doc.findtext('model', 'unknown'),
                                'dataRevision': doc.findtext('dataRevision', '1.0'),
                                'name': doc.findtext('n', 'XMC-2')
                            }
                            
                            # Extract control information
                            control = doc.find('control')
                            if control is not None:
                                # Save control port
                                control_port = control.findtext('controlPort')
                                if control_port:
                                    self._transponder_port = int(control_port)
                                    
                                # Save notification port
                                notify_port = control.findtext('notifyPort')
                                if notify_port:
                                    self._config.notify_port = int(notify_port)
                                    
                                # Save protocol version
                                protocol_version = control.findtext('version')
                                if protocol_version:
                                    discovery_result['protocol'] = protocol_version
                                    
                                # Save keepalive interval
                                keepalive = control.findtext('keepAlive')
                                if keepalive:
                                    self._config.keepalive_interval = int(keepalive)
                                    discovery_result['keepalive'] = keepalive
                            
                            _LOGGER.debug("Extracted device info: %s", discovery_result)
                        elif root_tag == 'Response':
                            for child in doc:
                                if child.tag == 'emotivaPing':
                                    discovery_result = {k: v for k, v in child.attrib.items()}
                                    _LOGGER.debug("Discovery attributes: %s", discovery_result)
                except Exception as e:
                    _LOGGER.error("Error parsing discovery response: %s", e)
                    discovery_result = {"status": "error", "message": f"Error parsing response: {e}"}
                    return discovery_result
                
                # Discovery successful
                discovery_result = {
                    "status": "success", 
                    "ip": self._ip, 
                    "port": self._transponder_port,
                    "info": discovery_result
                }
                
            except asyncio.TimeoutError:
                _LOGGER.warning("Discovery timed out after %s seconds", timeout)
                discovery_result = {"status": "timeout", "message": f"Discovery timed out after {timeout} seconds"}
            except asyncio.CancelledError:
                _LOGGER.warning("Discovery cancelled")
                discovery_result = {"status": "cancelled", "message": "Discovery cancelled"}
            except Exception as e:
                _LOGGER.error("Error during discovery: %s", e)
                discovery_result = {"status": "error", "message": str(e)}
            finally:
                # Remove the reader
                loop.remove_reader(response_sock.fileno())
                
        except Exception as e:
            _LOGGER.error("Error during discovery setup: %s", e)
            discovery_result = {"status": "error", "message": str(e)}
        finally:
            response_sock.close()
        
        # After successful discovery, set up the notification listener
        # and subscribe to default notifications
        if discovery_result.get("status") == "success" and self._callback:
            try:
                await self._ensure_notification_listener()
                # Subscribe to default notification types from config
                if hasattr(self._config, 'default_subscriptions') and self._config.default_subscriptions:
                    await self.subscribe_to_notifications(self._config.default_subscriptions)
            except Exception as e:
                _LOGGER.warning("Error setting up default notifications: %s", e)
        
        # Return the discovery result
        return discovery_result

    async def _check_keepalive(self) -> None:
        """Check if we've missed too many keepalives."""
        current_time = time.time()
        # Convert interval from ms to seconds
        interval_seconds = self._config.keepalive_interval / 1000.0
        
        # Check if we've exceeded the max missed keepalives
        if current_time - self._last_keepalive > interval_seconds * self._config.max_missed_keepalives:
            _LOGGER.warning("Missed %d keepalives, device may be offline", self._config.max_missed_keepalives)
            self._missed_keepalives += 1
            
            # Reset last keepalive to prevent repeated warnings
            self._last_keepalive = current_time
            
            # Try to rediscover the device
            try:
                await self.discover()
            except Exception as e:
                _LOGGER.error("Failed to rediscover device: %s", e)

    def set_callback(self, callback: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """
        Set a callback function to handle notification messages.
        
        Args:
            callback: Function to call with notification data
        """
        self._callback = callback
        _LOGGER.debug("Set notification callback")
        
        # If we already completed discovery, set up the notification listener
        # and subscribe to default notifications
        if self._discovery_complete and callback:
            asyncio.create_task(self._setup_default_notifications())
    
    async def _setup_default_notifications(self) -> None:
        """Set up default notifications after callback is set."""
        try:
            await self._ensure_notification_listener()
            # Subscribe to default notification types from config
            if hasattr(self._config, 'default_subscriptions') and self._config.default_subscriptions:
                await self.subscribe_to_notifications(self._config.default_subscriptions)
        except Exception as e:
            _LOGGER.warning("Error setting up default notifications: %s", e)

    async def _ensure_notification_listener(self) -> None:
        """
        Ensure notification listener is running.
        
        This registers the device with the AsyncEmotivaNotifier if not already done.
        """
        if not self._notification_registered and self._callback:
            try:
                # Register with the async notifier
                await self._notifier.register(
                    self._ip,
                    self._config.notify_port,
                    self._handle_notify
                )
                self._notification_registered = True
                _LOGGER.debug("Registered notification listener for %s on port %d", 
                             self._ip, self._config.notify_port)
            except Exception as e:
                _LOGGER.error("Failed to register notification listener: %s", e)
                # We'll continue without notifications

    def _handle_notify(self, data: bytes) -> None:
        """
        Internal method to handle incoming notifications from the device.
        
        This method processes the notification data and calls the registered callback
        with the relevant state changes.
        
        Args:
            data (bytes): Raw notification data from the device
        """
        _LOGGER.debug("Received notification from %s", self._ip)
        doc = parse_response(data)
        
        if doc is None:
            _LOGGER.error("Failed to parse notification data")
            return
            
        # Check if this is actually an acknowledgment response
        if doc.tag == 'emotivaAck':
            _LOGGER.debug("Received acknowledgment message from %s", self._ip)
            return
            
        # Handle notification message
        if doc.tag == 'emotivaNotify':
            # Check sequence number
            sequence = doc.get('sequence')
            if sequence is not None:
                seq_num = int(sequence)
                if seq_num <= self._sequence_number:
                    _LOGGER.warning("Received out-of-order notification from %s: %d <= %d",
                                 self._ip, seq_num, self._sequence_number)
                self._sequence_number = seq_num
            
            changed = {}
            for el in doc:
                if el.tag == 'property':
                    prop_name = el.get('name')
                    if prop_name in NOTIFY_EVENTS:
                        if prop_name == 'keepalive':
                            self._last_keepalive = time.time()
                            self._missed_keepalives = 0
                        changed[prop_name] = el.attrib
                    else:
                        _LOGGER.warning("Received property %s not in NOTIFY_EVENTS", prop_name)
                elif el.tag in NOTIFY_EVENTS:
                    # Handle legacy format
                    if el.tag == 'keepalive':
                        self._last_keepalive = time.time()
                        self._missed_keepalives = 0
                    changed[el.tag] = el.attrib
                    
            if changed and self._callback:
                self._callback(changed)
                
        elif doc.tag == 'emotivaMenuNotify' or doc.tag == 'emotivaBarNotify':
            # Handle other notification types if needed
            _LOGGER.debug("Received %s message from %s", doc.tag, self._ip)
            
        else:
            _LOGGER.warning("Received unknown message type from %s: %s", self._ip, doc.tag)
            
    async def ensure_ip_is_valid(self) -> None:
        """
        Ensure the IP address is valid.
        
        This method ensures the IP address is in a valid format
        by validating it directly with inet_aton.
        """
        try:
            # Simply validate if it's a valid IP format
            socket.inet_aton(self._ip)
            _LOGGER.debug("IP address %s validated", self._ip)
        except OSError:
            _LOGGER.error("Invalid IP address format: %s", self._ip)
            raise
                
    async def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a command to the Emotiva device asynchronously.
        
        Args:
            cmd (str): Command to send
            params (Optional[Dict[str, Any]]): Command parameters
            
        Returns:
            Dict[str, Any]: Command response or default response if no acknowledgment is received
        """
        # Check if device discovery is complete
        if not self._discovery_complete or self._transponder_port is None:
            _LOGGER.debug("Device not discovered yet, attempting discovery")
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                _LOGGER.error("Failed to discover device: %s", discovery_result.get("message"))
                return {"status": "error", "message": f"Device discovery failed: {discovery_result.get('message')}"}
        
        # Ensure IP address is valid
        await self.ensure_ip_is_valid()
        
        # Format the command request
        request = self._format_command_request(cmd, params)
        
        try:
            # Create a UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self._timeout)
            
            # Send the request to the control port
            _LOGGER.debug("Sending command to %s:%d: %s", self._ip, self._transponder_port, request)
            sock.sendto(request, (self._ip, self._transponder_port))
            
            # Wait for response if acknowledgment was requested
            ack_requested = params and params.get("ack", "").lower() == "yes"
            
            if ack_requested:
                try:
                    # Set a timeout for reading the response
                    data, _ = sock.recvfrom(4096)
                    
                    # Parse the response
                    return self._parse_command_response(data, cmd)
                    
                except socket.timeout:
                    _LOGGER.warning("Timeout waiting for command acknowledgment")
                    return {"status": "timeout", "message": "No acknowledgment received within timeout period"}
            else:
                # Don't wait for acknowledgment if not requested
                return {
                    "status": "sent", 
                    "message": "Command sent successfully. State changes will be reflected in notifications."
                }
                
        except Exception as e:
            _LOGGER.error("Error sending command: %s", e)
            return {"status": "error", "message": str(e)}
        finally:
            if 'sock' in locals():
                sock.close()
        
        # Default response for successful command
        return {
            "status": "sent", 
            "message": "Command sent successfully"
        }

    def _format_command_request(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Format a command request as XML.
        
        Args:
            cmd: Command name
            params: Command parameters
            
        Returns:
            Formatted request as bytes
        """
        # Format the command request by directly creating XML
        # according to the specification format
        root = ET.Element("emotivaControl")
        
        # Create the command element with attributes
        cmd_element = ET.SubElement(root, cmd)
        
        # Add parameters as attributes
        if params:
            for key, value in params.items():
                cmd_element.set(key, str(value))
                
        # Ensure "value" attribute is present
        if params and "value" not in params:
            cmd_element.set("value", "0")
        
        # Convert to XML string
        xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
        return xml_declaration.encode('utf-8') + ET.tostring(root, encoding='utf-8')
    
    def _parse_command_response(self, data: bytes, cmd: str) -> Dict[str, Any]:
        """
        Parse command response data.
        
        Args:
            data: Response data
            cmd: Command that was sent
            
        Returns:
            Parsed response data
        """
        try:
            doc = parse_response(data)
            if doc is not None:
                # Check for error response
                if doc.tag == 'Error':
                    error_message = doc.text if doc.text else "Unknown error"
                    _LOGGER.error("Error response: %s", error_message)
                    return {"status": "error", "message": error_message}
                
                # Success response
                if doc.tag == 'emotivaAck':
                    # Extract command acknowledgment
                    for child in doc:
                        if child.tag == cmd:
                            status = child.get('status')
                            if status == 'ack':
                                return {"status": "success", "message": f"Command {cmd} acknowledged"}
                            else:
                                return {"status": "error", "message": f"Command {cmd} not acknowledged"}
                    
                    return {"status": "unknown", "message": "Received acknowledgment but couldn't find command status"}
                
                # Other response type
                return {"status": "received", "response": str(doc)}
                
        except Exception as e:
            _LOGGER.error("Error parsing command response: %s", e)
            return {"status": "error", "message": f"Error parsing command response: {e}"}
        
        return {"status": "unknown", "message": "Unknown response format"}

    async def set_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set audio processing mode with notification handling.
        
        Args:
            mode: Audio processing mode name
            
        Returns:
            Command response with notification handling
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Map mode to device identifier if needed
        device_mode = MODE_PRESETS.get(mode.lower(), mode)
        
        # Subscribe to mode notifications
        await self.subscribe_to_notifications(["mode"])
        
        # Send the command with notification handling
        return await self.manage_device("audioMode", {"value": device_mode})

    async def set_input(self, input_source: str) -> Dict[str, Any]:
        """
        Set the input source with notification handling.
        
        Args:
            input_source: Input source name or identifier
            
        Returns:
            Command response with notification handling
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
            
        # Map input source to device identifier if needed
        device_input = INPUT_SOURCES.get(input_source.lower(), input_source)
        
        # Subscribe to input and video/audio input notifications
        await self.subscribe_to_notifications(["input", "video_input", "audio_input"])
        
        # Send the command with notification handling
        return await self.manage_device("input", {"source": device_input})

    async def set_source(self, source: str) -> Dict[str, Any]:
        """
        Set the source using the source command (alternative to input) with notification handling.
        
        Args:
            source: Source identifier
            
        Returns:
            Command response with notification handling
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
            
        # Map source to device identifier if needed
        device_source = INPUT_SOURCES.get(source.lower(), source)
        
        # Subscribe to input and video/audio input notifications
        await self.subscribe_to_notifications(["input", "video_input", "audio_input"])
        
        # Send the command with notification handling
        return await self.manage_device("source", {"value": device_source})

    async def set_movie_mode(self) -> Dict[str, Any]:
        """
        Set the movie preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("movie", {"value": 0})
        
    async def set_music_mode(self) -> Dict[str, Any]:
        """
        Set the music preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("music", {"value": 0})
        
    async def set_stereo_mode(self) -> Dict[str, Any]:
        """
        Set the stereo preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("stereo", {"value": 0})
        
    async def set_direct_mode(self) -> Dict[str, Any]:
        """
        Set the direct preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("direct", {"value": 0})
        
    async def set_dolby_mode(self) -> Dict[str, Any]:
        """
        Set the Dolby preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("dolby", {"value": 0})
        
    async def set_dts_mode(self) -> Dict[str, Any]:
        """
        Set the DTS preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("dts", {"value": 0})
        
    async def set_all_stereo_mode(self) -> Dict[str, Any]:
        """
        Set the all stereo preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("all_stereo", {"value": 0})
        
    async def set_auto_mode(self) -> Dict[str, Any]:
        """
        Set the auto preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("auto", {"value": 0})
        
    async def set_reference_stereo_mode(self) -> Dict[str, Any]:
        """
        Set the reference stereo preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("reference_stereo", {"value": 0})
        
    async def set_surround_mode(self) -> Dict[str, Any]:
        """
        Set the surround preset mode with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        await self.subscribe_to_notifications(["mode"])
        return await self.manage_device("surround", {"value": 0})

    async def get_zone2_power(self) -> Dict[str, Any]:
        """
        Get the power status of Zone 2 with notification handling.
        
        This method sends a request to get the current Zone 2 power status
        and processes the resulting notifications.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Subscribe to zone2_power notifications if we have a callback
        if self._callback:
            await self.subscribe_to_notifications(["zone2_power"])
            
            # Create a dummy command that will just trigger the zone2_power update
            return await self.manage_device("zone2_power", {"ack": "no"})
        else:
            # Just request zone 2 power update without notification handling
            return await self.update_properties(["zone2_power"])
        
    async def set_zone2_power_on(self) -> Dict[str, Any]:
        """
        Turn on Zone 2 with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Subscribe to notifications first
        await self.subscribe_to_notifications(["zone2_power"])
        
        # Use manage_device for command and notification handling
        return await self.manage_device("zone2_power", {"value": "on", "ack": "yes"})
        
    async def set_zone2_power_off(self) -> Dict[str, Any]:
        """
        Turn off Zone 2 with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Subscribe to notifications first
        await self.subscribe_to_notifications(["zone2_power"])
        
        # Use manage_device for command and notification handling
        return await self.manage_device("zone2_power", {"value": "off", "ack": "yes"})
        
    async def toggle_zone2_power(self) -> Dict[str, Any]:
        """
        Toggle Zone 2 power with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Subscribe to notifications first
        await self.subscribe_to_notifications(["zone2_power"])
        
        # Use manage_device for command and notification handling
        return await self.manage_device("zone2_power", {"value": "0", "ack": "yes"})

    async def subscribe_to_notifications(self, event_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Subscribe to device notifications.
        
        Args:
            event_types: Optional list of event types to subscribe to
                        (default includes common ones like power, volume, etc.)
                    
        Returns:
            Dict with subscription result
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": f"Device discovery failed: {discovery_result.get('message')}"}
                
        # Default to common notifications if not specified
        if not event_types:
            event_types = ["power", "zone2_power", "volume", "source", "audio_bitstream", "audio_bits", "video_input", "video_format"]
        
        # Filter out events we've already subscribed to
        new_events = [event for event in event_types if event not in self._subscribed_events]
        
        # If all events are already subscribed to, just return success
        if not new_events:
            return {
                "status": "success", 
                "message": "All events already subscribed to"
            }
        
        # Create XML structure for subscription
        root = ET.Element("emotivaSubscription")
        root.set("protocol", PROTOCOL_VERSION)
        
        # Add property elements as per specification
        for event_type in new_events:
            # Handle common property aliases
            if event_type == "source":
                # "source" is likely "input" in NOTIFY_EVENTS
                if "input" in NOTIFY_EVENTS:
                    ET.SubElement(root, "input")
                    self._subscribed_events.add("input")
                else:
                    _LOGGER.warning("Cannot map 'source' to a known property")
            elif event_type in NOTIFY_EVENTS:
                ET.SubElement(root, event_type)
                self._subscribed_events.add(event_type)
            else:
                _LOGGER.warning("Ignoring unknown notification event type: %s", event_type)
        
        # If no valid events to subscribe to, return early
        if len(root) == 0:
            return {
                "status": "warning", 
                "message": "No valid events to subscribe to"
            }
        
        # Convert to XML string with XML declaration
        xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
        request = xml_declaration.encode('utf-8') + ET.tostring(root, encoding='utf-8')
        
        # Set up notification listener before sending subscription
        if self._callback and not self._notification_registered:
            try:
                await self._ensure_notification_listener()
                _LOGGER.debug("Notification listener set up on port %d", self._config.notify_port)
            except Exception as e:
                _LOGGER.error("Error setting up notification listener: %s", e)
                
        # Create and use UDP socket directly
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self._timeout)
            _LOGGER.debug("Sending subscription request for %d new events to %s:%d", 
                         len(new_events), self._ip, self._transponder_port)
            sock.sendto(request, (self._ip, self._transponder_port))
            return {
                "status": "sent", 
                "message": f"Subscription request for {len(new_events)} new events sent. Subscription will be confirmed when notifications are received."
            }
        except Exception as e:
            _LOGGER.error("Error sending subscription request: %s", e)
            return {"status": "error", "message": str(e)}
        finally:
            sock.close()

    async def switch_to_hdmi(self, hdmi_number: int) -> Dict[str, Any]:
        """
        Switch to a specific HDMI source using unified command and notification handling.
        
        This method tries multiple approaches to set both video and audio inputs 
        to the specified HDMI input, coordinating command sending and notification receiving.
        
        Args:
            hdmi_number (int): The HDMI input number (1-8)
            
        Returns:
            Dict[str, Any]: Command response with result status
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Validate HDMI number
        if not 1 <= hdmi_number <= 8:
            return {"status": "error", "message": f"Invalid HDMI input: {hdmi_number}. Must be between 1 and 8."}
            
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Get the input name from our mappings
        input_id = f"hdmi{hdmi_number}"
        input_name = INPUT_SOURCES.get(input_id, f"HDMI {hdmi_number}")
        
        _LOGGER.debug("Attempting to switch to HDMI %d using unified approach", hdmi_number)
        
        # Subscribe to all relevant notifications
        await self.subscribe_to_notifications(["audio_input", "video_input", "input"])
        
        # Method 1: Try direct hdmiX command with notification handling
        _LOGGER.debug("Trying direct hdmi%d command with notification handling", hdmi_number)
        
        primary_result = await self.manage_device(f"hdmi{hdmi_number}", {"value": "0"})
        
        # Check if successful via notifications - give a short delay for notifications to arrive
        await asyncio.sleep(1)
        
        # If primary method wasn't successful (determined by checking callback data), try method 2
        # Try method 2: separate video_input and audio_input commands
        _LOGGER.debug("Trying separate video_input and audio_input commands with notification handling")
        video_result = await self.manage_device("video_input", {"value": f"hdmi{hdmi_number}"})
        audio_result = await self.manage_device("audio_input", {"value": f"hdmi{hdmi_number}"})
        
        return {
            "status": "complete",
            "message": f"Attempted to switch to {input_name} using unified approach",
            "primary_result": primary_result,
            "video_result": video_result,
            "audio_result": audio_result
        }

    async def switch_to_source(self, source_command: str) -> Dict[str, Any]:
        """
        Switch to a specific source using unified command and notification handling.
        
        This method attempts to set the source using various methods, with proper
        coordination between command sending and notification handling.
        
        Args:
            source_command (str): Source identifier (e.g., hdmi1, analog1, etc.)
            
        Returns:
            Dict[str, Any]: Command response with result status
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Try to map the source to a known format
        source_id = source_command.strip().lower()
        
        # If it's an HDMI source with a number, use the specialized method
        if source_id.startswith('hdmi') and len(source_id) > 4:
            try:
                hdmi_number = int(source_id[4:])
                if 1 <= hdmi_number <= 8:
                    return await self.switch_to_hdmi(hdmi_number)
            except ValueError:
                # Not a valid HDMI number, continue with generic approach
                _LOGGER.debug("Not a valid HDMI number format: %s", source_id)
                
        # Get the source name for logging
        source_name = INPUT_SOURCES.get(source_id, source_id.upper())
        _LOGGER.debug("Attempting to set source to %s using unified approach", source_name)
        
        # Subscribe to notifications
        await self.subscribe_to_notifications(["input", "video_input", "audio_input"])
        
        # Use manage_device to try source command with notification handling
        primary_result = await self.manage_device("source", {"value": source_id})
        
        # Check if successful via notifications - give a short delay for notifications to arrive
        await asyncio.sleep(1)
        
        # If needed, try alternative input command
        input_result = await self.manage_device("input", {"source": source_id})
        
        return {
            "status": "complete",
            "message": f"Attempted to switch to {source_name} using unified approach",
            "primary_result": primary_result,
            "input_result": input_result
        }

    async def close(self) -> None:
        """
        Close all connections and clean up resources.
        This should be called when done with the Emotiva instance.
        """
        try:
            # Clean up notification listener
            try:
                if self._notification_registered:
                    # Try the normal unregister path first
                    try:
                        await asyncio.wait_for(
                            self._notifier.unregister(self._ip),
                            timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        _LOGGER.warning("Unregister timed out, proceeding with force cleanup")
                    except Exception as e:
                        _LOGGER.warning("Error during unregister: %s, proceeding with force cleanup", e)
                        
                    self._notification_registered = False
                
                # Clean up notifier - use force_stop_listener if available
                if hasattr(self._notifier, 'force_stop_listener'):
                    await self._notifier.force_stop_listener()
                
                # Always run the regular cleanup in case force_stop didn't work
                try:
                    await asyncio.wait_for(
                        self._notifier.cleanup(),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning("Notifier cleanup timed out")
                except Exception as e:
                    _LOGGER.warning("Error during notifier cleanup: %s", e)
            except Exception as e:
                _LOGGER.warning("Error during notification cleanup: %s", e)
            
            _LOGGER.debug("Closed Emotiva connection to %s", self._ip)
        except Exception as e:
            _LOGGER.debug("Error during cleanup: %s", e)
            
    def __del__(self):
        """Clean up resources when the object is destroyed."""
        try:
            # Use asyncio.run to call the async close method, but only in non-async contexts
            # This is not ideal, but provides some cleanup in synchronous contexts
            if not asyncio.get_event_loop().is_running():
                asyncio.run(self.close())
        except Exception as e:
            _LOGGER.debug("Error during cleanup: %s", e)

    async def update_properties(self, properties: List[str]) -> Dict[str, Any]:
        """
        Request updates for specific properties.
        
        This method sends an update request for the specified properties,
        which will trigger notifications if subscribed.
        
        Args:
            properties: List of property names to update
            
        Returns:
            Dict[str, Any]: Update response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": f"Device discovery failed: {discovery_result.get('message')}"}
        
        # Ensure IP address is valid
        await self.ensure_ip_is_valid()
        
        # Validate and map properties
        mapped_properties = []
        for prop in properties:
            # Handle common property aliases
            if prop == "source":
                # "source" is likely "input" in NOTIFY_EVENTS
                if "input" in NOTIFY_EVENTS:
                    mapped_properties.append("input")
                else:
                    _LOGGER.warning("Cannot map 'source' to a known property")
            elif prop in NOTIFY_EVENTS:
                mapped_properties.append(prop)
            else:
                _LOGGER.warning("Ignoring unknown property: %s", prop)
        
        if not mapped_properties:
            return {"status": "error", "message": "No valid properties specified for update"}
        
        # Create XML structure for update
        root = ET.Element("emotivaUpdate")
        root.set("protocol", PROTOCOL_VERSION)
        
        # Add property elements
        for prop in mapped_properties:
            ET.SubElement(root, prop)
        
        # Convert to XML string with XML declaration
        xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
        request = xml_declaration.encode('utf-8') + ET.tostring(root, encoding='utf-8')
        
        try:
            # Create a UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self._timeout)
            
            # Send the request to the control port
            _LOGGER.debug("Sending update request to %s:%d for properties: %s", 
                         self._ip, self._transponder_port, mapped_properties)
            sock.sendto(request, (self._ip, self._transponder_port))
            
            return {
                "status": "sent", 
                "message": f"Update request sent for {len(mapped_properties)} properties. Current values will be delivered via notification."
            }
                
        except Exception as e:
            _LOGGER.error("Error sending update request: %s", e)
            return {"status": "error", "message": str(e)}
        finally:
            if 'sock' in locals():
                sock.close()

    async def manage_device(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Unified method to handle both sending commands and receiving notifications.
        
        This method will:
        1. Ensure the notification listener is running if callback is set
        2. Send the command to the device
        3. Concurrently wait for command response and handle notifications
        
        Args:
            command: Command to send
            params: Optional parameters for the command
            
        Returns:
            Dict[str, Any]: Command response
        """
        # Ensure callback is set up to receive notifications
        if not self._callback:
            _LOGGER.warning("No callback set for handling notifications")
            return await self.send_command(command, params)
        
        # Ensure the notification listener is running
        await self._ensure_notification_listener()
        
        # Create a task for sending the command
        command_task = asyncio.create_task(self.send_command(command, params))
        
        # Create a task for handling notifications (using a dummy function)
        # This ensures the notification listener keeps running while we wait for the command response
        async def dummy_wait():
            # Wait for a short time to ensure notifications have a chance to be processed
            await asyncio.sleep(0.5)
            return {"status": "notification_listener_running"}
        
        notification_task = asyncio.create_task(dummy_wait())
        
        # Wait for both tasks to complete
        done, pending = await asyncio.wait(
            [command_task, notification_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Get command result
        command_result = await command_task
        
        # Cancel the notification task if it's still pending
        for task in pending:
            task.cancel()
        
        return command_result

    async def set_power_on(self) -> Dict[str, Any]:
        """
        Turn on Zone 1 (main zone) power with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Subscribe to notifications first
        await self.subscribe_to_notifications(["power"])
        
        # Use manage_device for command and notification handling
        return await self.manage_device("power_on", {"value": "0", "ack": "yes"})
        
    async def set_power_off(self) -> Dict[str, Any]:
        """
        Turn off Zone 1 (main zone) power with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Subscribe to notifications first
        await self.subscribe_to_notifications(["power"])
        
        # Use manage_device for command and notification handling
        return await self.manage_device("power_off", {"value": "0", "ack": "yes"})
        
    async def toggle_power(self) -> Dict[str, Any]:
        """
        Toggle Zone 1 (main zone) power with notification handling.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Subscribe to notifications first
        await self.subscribe_to_notifications(["power"])
        
        # Use manage_device for command and notification handling
        return await self.manage_device("power", {"value": "0", "ack": "yes"})
    
    async def get_power(self) -> Dict[str, Any]:
        """
        Get the power status of Zone 1 (main zone) with notification handling.
        
        This method sends a request to get the current Zone 1 power status
        and processes the resulting notifications.
        
        Returns:
            Dict[str, Any]: Command response with notification handling
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = await self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Subscribe to power notifications if we have a callback
        if self._callback:
            await self.subscribe_to_notifications(["power"])
            
            # Create a dummy command that will just trigger the power update
            return await self.manage_device("power", {"ack": "no"})
        else:
            # Just request power update without notification handling
            return await self.update_properties(["power"])
