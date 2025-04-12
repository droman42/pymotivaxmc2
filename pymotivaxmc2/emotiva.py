"""
Emotiva A/V Receiver Control Module

This module provides a Python interface for controlling Emotiva A/V receivers over the network.
It implements the Emotiva UDP protocol for device discovery, command sending, and event notification.
"""

import socket
import time
import logging
import threading
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta

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
from .network import SocketManager
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
        _lock (threading.Lock): Thread lock for thread-safe operations
        _socket_manager (SocketManager): Manages network communication
        _config (EmotivaConfig): Configuration object
        _last_keepalive (datetime): Timestamp of last keepalive received
        _missed_keepalives (int): Number of missed keepalives
        _sequence_number (int): Current sequence number for notifications
        _input_mappings (Dict[str, str]): Mapping of custom input names to standard input identifiers
    """
    
    def __init__(self, config: EmotivaConfig) -> None:
        """
        Initialize the Emotiva controller.
        
        Args:
            config (EmotivaConfig): Configuration for the Emotiva device
        """
        self._config = config
        self._ip: str = config.ip
        self._timeout: int = config.timeout
        self._transponder_port: Optional[int] = None
        self._callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._lock: threading.Lock = threading.Lock()
        self._socket_manager: SocketManager = SocketManager()
        self._last_keepalive: Optional[datetime] = None
        self._missed_keepalives: int = 0
        self._sequence_number: int = 0
        self._input_mappings: Dict[str, str] = {}
        
        _LOGGER.debug("Initialized with ip: %s, timeout: %d", self._ip, self._timeout)

    def _query_input_names(self, custom_mappings: Optional[Dict[str, str]] = None) -> None:
        """
        Initialize input mappings with default values and optionally add custom mappings.
        
        Args:
            custom_mappings (Optional[Dict[str, str]]): Optional dictionary of custom input name mappings.
                Keys should be standard input identifiers, values should be custom names.
                If None, only default mappings will be used.
        
        This method sets up the initial mappings between standard input identifiers
        and their display names. Custom names can be provided through the custom_mappings
        parameter or added later through set_input or set_source methods.
        """
        # Initialize with default mappings
        for input_id, display_name in INPUT_SOURCES.items():
            self._input_mappings[input_id] = display_name
            self._input_mappings[display_name] = input_id
            
        # Add custom mappings if provided
        if custom_mappings is not None:
            for input_id, custom_name in custom_mappings.items():
                if input_id in INPUT_SOURCES:
                    self._input_mappings[input_id] = custom_name
                    self._input_mappings[custom_name] = input_id
                else:
                    _LOGGER.warning(
                        "Ignoring custom mapping for unknown input identifier: %s",
                        input_id
                    )
            
        _LOGGER.debug("Input mappings initialized: %s", self._input_mappings)

    def discover(self, custom_mappings: Optional[Dict[str, str]] = None) -> int:
        """
        Discover the Emotiva device and get its transponder port.
        
        Args:
            custom_mappings (Optional[Dict[str, str]]): Optional dictionary of custom input name mappings.
                Keys should be standard input identifiers, values should be custom names.
                If None, only default mappings will be used.
        
        This method sends a discovery request to the device and waits for a response
        containing the transponder port number that will be used for subsequent commands.
        
        Returns:
            int: The transponder port number for command communication
            
        Raises:
            InvalidTransponderResponseError: If no response is received or the response is invalid
        """
        _LOGGER.debug("Starting device discovery for %s", self._ip)
        
        # Create a temporary socket for discovery
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self._timeout)
        
        try:
            # Try binding to the response port
            try:
                sock.bind(('', self._config.discover_response_port))
                _LOGGER.debug("Successfully bound to port %d", self._config.discover_response_port)
            except OSError as e:
                _LOGGER.error("Failed to bind to port %d: %s", self._config.discover_response_port, e)
                raise InvalidTransponderResponseError(f"Failed to bind to port {self._config.discover_response_port}: {e}")

            # Format and send the discovery request with protocol version
            request = format_request('emotivaPing', {'protocol': PROTOCOL_VERSION})
            _LOGGER.debug("Sending discovery request to %s:%d", self._ip, self._config.discover_request_port)
            _LOGGER.debug("Request content: %s", request)
            sock.sendto(request, (self._ip, self._config.discover_request_port))

            # Wait for response
            try:
                data, addr = sock.recvfrom(4096)
                _LOGGER.debug("Received discovery response from %s:%d", addr[0], addr[1])
                _LOGGER.debug("Response content: %s", data)
            except socket.timeout:
                _LOGGER.error("Timeout waiting for discovery response from %s. Make sure the device is powered on and connected to the network.", self._ip)
                raise InvalidTransponderResponseError('No response from device. Please ensure the device is powered on and connected to the network.')
            except OSError as e:
                _LOGGER.error("Error receiving response: %s", e)
                raise InvalidTransponderResponseError(f"Error receiving response: {e}")

            # Parse and validate the response
            doc = parse_response(data)
            if not validate_response(doc, "emotivaTransponder"):
                _LOGGER.error("Invalid discovery response from %s: %s", self._ip, data)
                raise InvalidTransponderResponseError('Invalid discovery response')

            # Extract transponder port and keepalive interval
            control = doc.find('control')
            if control is not None:
                self._transponder_port = int(control.find('controlPort').text)
                keepalive = control.find('keepAlive')
                if keepalive is not None:
                    self._config.keepalive_interval = int(keepalive.text)
                    _LOGGER.debug("Device keepalive interval: %d ms", self._config.keepalive_interval)
            else:
                _LOGGER.error("Missing control information in discovery response")
                raise InvalidTransponderResponseError('Missing control information in discovery response')

            # Initialize input mappings with optional custom mappings
            self._query_input_names(custom_mappings)

            _LOGGER.info("Successfully discovered device %s on port %d", self._ip, self._transponder_port)
            return self._transponder_port

        finally:
            sock.close()

    def _check_keepalive(self) -> None:
        """
        Check if the device is still alive based on keepalive messages.
        
        Raises:
            DeviceOfflineError: If too many keepalives have been missed
        """
        if self._last_keepalive is None:
            return
            
        now = datetime.now()
        expected_interval = timedelta(milliseconds=self._config.keepalive_interval)
        missed_intervals = (now - self._last_keepalive) // expected_interval
        
        if missed_intervals > 0:
            self._missed_keepalives += missed_intervals
            _LOGGER.warning("Missed %d keepalive intervals from %s", missed_intervals, self._ip)
            
            if self._missed_keepalives >= self._config.max_missed_keepalives:
                raise DeviceOfflineError(f"Device {self._ip} appears to be offline")

    def set_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Set the callback function for handling device notifications.
        
        The callback function will be called whenever the device sends a notification
        about state changes (power, volume, input, etc.).
        
        Args:
            callback (Callable[[Dict[str, Any]], None]): Function to handle notifications.
        """
        _LOGGER.debug("Setting notification callback for %s", self._ip)
        self._callback = callback
        if self._transponder_port:
            self._socket_manager.register_device(
                self._ip,
                self._transponder_port,
                self._handle_notify
            )
            _LOGGER.debug("Registered notification handler for %s on port %d", 
                         self._ip, self._transponder_port)

    def _handle_notify(self, data: bytes) -> None:
        """
        Internal method to handle incoming notifications from the device.
        
        This method processes the notification data and calls the registered callback
        with the relevant state changes.
        
        Args:
            data (bytes): Raw notification data from the device
        """
        _LOGGER.debug("Received notification from %s: %s", self._ip, data)
        doc = parse_response(data)
        
        # Check sequence number
        sequence = doc.get('sequence')
        if sequence is not None:
            seq_num = int(sequence)
            if seq_num <= self._sequence_number:
                _LOGGER.warning("Received out-of-order notification from %s: %d <= %d",
                              self._ip, seq_num, self._sequence_number)
            self._sequence_number = seq_num
        
        if not validate_response(doc, "Notify"):
            _LOGGER.warning("Invalid notification format from %s: %s", self._ip, data)
            return
            
        changed = {}
        for el in doc:
            if el.tag in NOTIFY_EVENTS:
                if el.tag == 'keepalive':
                    self._last_keepalive = datetime.now()
                    self._missed_keepalives = 0
                changed[el.tag] = el.attrib
                
        if changed and self._callback:
            _LOGGER.debug("Processing state changes for %s: %s", self._ip, changed)
            self._callback(changed)

    def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a command to the Emotiva device.
        
        This method sends a command to the device and waits for a response.
        The command and parameters are formatted according to the Emotiva protocol.
        
        Args:
            cmd (str): Command name to send
            params (Optional[Dict[str, Any]]): Command parameters. Defaults to None.
            
        Returns:
            Dict[str, Any]: Command response data
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or no response is received
            DeviceOfflineError: If the device appears to be offline
        """
        if self._transponder_port is None:
            _LOGGER.error("Cannot send command to %s: device not discovered", self._ip)
            raise InvalidTransponderResponseError('Device not discovered yet')
            
        # Check device status
        self._check_keepalive()
            
        _LOGGER.debug("Sending command '%s' to %s:%d with params: %s", 
                     cmd, self._ip, self._transponder_port, params)
                     
        req = format_request('emotivaControl', [(cmd, params or {})])
        self._socket_manager.send_data(self._ip, self._transponder_port, req)
        
        # Create a temporary socket for receiving the response
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self._timeout)
        
        try:
            data, _ = sock.recvfrom(4096)
            _LOGGER.debug("Received response from %s: %s", self._ip, data)
        except socket.timeout:
            _LOGGER.error("Timeout waiting for response from %s", self._ip)
            raise InvalidTransponderResponseError('Timeout waiting for response')
        finally:
            sock.close()

        doc = parse_response(data)
        response = extract_command_response(doc, cmd)
        if response is None:
            raise InvalidTransponderResponseError('Invalid command response')
            
        return response

    def set_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set the audio processing mode.
        
        Args:
            mode (str): Mode to set (e.g., 'stereo', 'direct', 'dolby', etc.)
            
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidModeError: If the specified mode is not valid
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        if mode not in MODE_PRESETS:
            raise InvalidModeError(f"Invalid mode: {mode}. Valid modes are: {list(MODE_PRESETS.keys())}")
            
        return self.send_command(mode, {"value": 0})
        
    def set_input(self, input_source: str) -> Dict[str, Any]:
        """
        Set the input source.
        
        Args:
            input_source (str): Input source to set (e.g., 'hdmi1', 'coax1', etc.)
                              Can be either a standard input identifier or a custom name
            
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidSourceError: If the specified input source is not valid
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # First check if it's a standard input identifier
        if input_source in INPUT_SOURCES:
            return self.send_command(input_source, {"value": 0})
            
        # If not a standard input, check if we have a mapping for it
        if input_source in self._input_mappings:
            input_id = self._input_mappings[input_source]
            if input_id in INPUT_SOURCES:
                return self.send_command(input_id, {"value": 0})
            
        # If we get here, it's neither a standard input nor a mapped custom name
        raise InvalidSourceError(
            f"Invalid input source: {input_source}. "
            f"Valid sources are: {list(INPUT_SOURCES.keys())}"
        )
        
    def set_source(self, source: str) -> Dict[str, Any]:
        """
        Set the source using the source command.
        
        Args:
            source (str): Source to set (e.g., 'hdmi1', 'coax1', etc.)
                        Can be either a standard input identifier or a custom name
            
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidSourceError: If the specified source is not valid
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # First check if it's a standard input identifier
        if source in INPUT_SOURCES:
            return self.send_command("source", {"value": source})
            
        # If not a standard input, check if we have a mapping for it
        if source in self._input_mappings:
            input_id = self._input_mappings[source]
            if input_id in INPUT_SOURCES:
                return self.send_command("source", {"value": input_id})
            
        # If we get here, it's neither a standard input nor a mapped custom name
        raise InvalidSourceError(
            f"Invalid source: {source}. "
            f"Valid sources are: {list(INPUT_SOURCES.keys())}"
        )
        
    def set_movie_mode(self) -> Dict[str, Any]:
        """
        Set the movie preset mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("movie", {"value": 0})
        
    def set_music_mode(self) -> Dict[str, Any]:
        """
        Set the music preset mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("music", {"value": 0})
        
    def set_stereo_mode(self) -> Dict[str, Any]:
        """
        Set the stereo mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("stereo", {"value": 0})
        
    def set_direct_mode(self) -> Dict[str, Any]:
        """
        Set the direct mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("direct", {"value": 0})
        
    def set_dolby_mode(self) -> Dict[str, Any]:
        """
        Set the Dolby mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("dolby", {"value": 0})
        
    def set_dts_mode(self) -> Dict[str, Any]:
        """
        Set the DTS mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("dts", {"value": 0})
        
    def set_all_stereo_mode(self) -> Dict[str, Any]:
        """
        Set the all stereo mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("all_stereo", {"value": 0})
        
    def set_auto_mode(self) -> Dict[str, Any]:
        """
        Set the auto mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("auto", {"value": 0})
        
    def set_reference_stereo_mode(self) -> Dict[str, Any]:
        """
        Set the reference stereo mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("reference_stereo", {"value": 0})
        
    def set_surround_mode(self) -> Dict[str, Any]:
        """
        Set the surround mode.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        return self.send_command("surround_mode", {"value": 0})

    def __del__(self):
        """Clean up resources when the object is destroyed."""
        self._socket_manager.stop()
