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

from .exceptions import (
    InvalidTransponderResponseError,
    InvalidSourceError,
    InvalidModeError
)
from .utils import format_request, parse_response, validate_response, extract_command_response
from .constants import DISCOVER_REQ_PORT, DISCOVER_RESP_PORT, NOTIFY_EVENTS
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
        _transponder_port (Optional[int]): Port number for command communication
        _callback (Optional[Callable]): Function to handle device notifications
        _lock (threading.Lock): Thread lock for thread-safe operations
        _socket_manager (SocketManager): Manages network communication
        _config (EmotivaConfig): Configuration object
    """
    
    def __init__(self, config: EmotivaConfig) -> None:
        """
        Initialize the Emotiva controller.
        
        Args:
            config (EmotivaConfig): Configuration for the Emotiva device
        """
        print(f"Initializing Emotiva with config: {config}")
        print(f"Config type: {type(config)}")
        print(f"Config attributes: {dir(config)}")
        
        self._config = config
        self._ip: str = config.ip
        self._timeout: int = config.timeout
        self._transponder_port: Optional[int] = None
        self._callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._lock: threading.Lock = threading.Lock()
        self._socket_manager: SocketManager = SocketManager()
        
        print(f"Initialized with ip: {self._ip}, timeout: {self._timeout}")

    def discover(self) -> int:
        """
        Discover the Emotiva device and get its transponder port.
        
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

            # Format and send the discovery request
            request = format_request('Request', {'Discover': ''})
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
            if not validate_response(doc, "Response") or doc.find('Discover') is None:
                _LOGGER.error("Invalid discovery response from %s: %s", self._ip, data)
                raise InvalidTransponderResponseError('Invalid discovery response')

            self._transponder_port = int(doc.find('Discover').attrib['port'])
            _LOGGER.info("Successfully discovered device %s on port %d", self._ip, self._transponder_port)
            return self._transponder_port

        finally:
            sock.close()

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
        if not validate_response(doc, "Notify"):
            _LOGGER.warning("Invalid notification format from %s: %s", self._ip, data)
            return
            
        changed = {}
        for el in doc:
            if el.tag in NOTIFY_EVENTS:
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
        """
        if self._transponder_port is None:
            _LOGGER.error("Cannot send command to %s: device not discovered", self._ip)
            raise InvalidTransponderResponseError('Device not discovered yet')
            
        _LOGGER.debug("Sending command '%s' to %s:%d with params: %s", 
                     cmd, self._ip, self._transponder_port, params)
                     
        req = format_request('Request', [(cmd, params or {})])
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

    def __del__(self):
        """Clean up resources when the object is destroyed."""
        self._socket_manager.stop()
