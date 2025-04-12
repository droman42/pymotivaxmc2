"""
Emotiva A/V Receiver Control Module

This module provides a Python interface for controlling Emotiva A/V receivers over the network.
It implements the Emotiva UDP protocol for device discovery, command sending, and event notification.
"""

import socket
import time
import logging
import threading
from typing import Optional, Dict, Any, Callable, List
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
            config: Configuration object with device settings
        """
        self._ip = config.ip
        self._config = config
        self._timeout = config.timeout
        self._transponder_port = None
        self._callback = None
        self._discovery_complete = False
        
        # Notification listener components
        self._listener_thread = None
        self._listener_socket = None
        self._listener_running = False
        
        # Keepalive status tracking
        self._last_keepalive = time.time()
        self._missed_keepalives = 0
        self._sequence_number = 0
        
        _LOGGER.debug("Initialized with ip: %s, timeout: %d", self._ip, self._timeout)

    def discover(self, timeout: float = 1.0) -> Dict[str, Any]:
        """
        Discover Emotiva device on the network.
        
        Args:
            timeout: Timeout in seconds to wait for device response.
            
        Returns:
            Dictionary with discovery results.
        """
        # Set a specified timeout for discovery
        self._timeout = timeout
        discovery_result = {}
        
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
            
            # Wait for response
            try:
                data, addr = response_sock.recvfrom(4096)
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
                    return {"status": "error", "message": f"Error parsing response: {e}"}
                
                # Discovery successful
                return {
                    "status": "success", 
                    "ip": self._ip, 
                    "port": self._transponder_port,
                    "device_info": discovery_result
                }
            
            except socket.timeout:
                _LOGGER.error("Timeout waiting for discovery response")
                return {"status": "error", "message": "Timeout waiting for response"}
                
        except Exception as e:
            _LOGGER.error("Error during device discovery: %s", e)
            return {"status": "error", "message": str(e)}
            
        finally:
            response_sock.close()

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

    def set_callback(self, callback: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """
        Set a callback for handling device notifications.
        
        Args:
            callback: Function to be called when state changes occur
        """
        self._callback = callback
        _LOGGER.debug("Notification callback set for %s", self._ip)

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
                            self._last_keepalive = datetime.now()
                            self._missed_keepalives = 0
                        changed[prop_name] = el.attrib
                    else:
                        _LOGGER.warning("Received property %s not in NOTIFY_EVENTS", prop_name)
                elif el.tag in NOTIFY_EVENTS:
                    # Handle legacy format
                    if el.tag == 'keepalive':
                        self._last_keepalive = datetime.now()
                        self._missed_keepalives = 0
                    changed[el.tag] = el.attrib
                    
            if changed and self._callback:
                self._callback(changed)
                
        elif doc.tag == 'emotivaMenuNotify' or doc.tag == 'emotivaBarNotify':
            # Handle other notification types if needed
            _LOGGER.debug("Received %s message from %s", doc.tag, self._ip)
            
        else:
            _LOGGER.warning("Received unknown message type from %s: %s", self._ip, doc.tag)

    def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a command to the Emotiva device.
        
        Args:
            cmd (str): Command to send
            params (Optional[Dict[str, Any]]): Command parameters
            
        Returns:
            Dict[str, Any]: Command response or default response if no acknowledgment is received
        """
        # Check if device discovery is complete
        if not self._discovery_complete or self._transponder_port is None:
            _LOGGER.debug("Device not discovered yet, attempting discovery")
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                _LOGGER.error("Failed to discover device: %s", discovery_result.get("message"))
                return {"status": "error", "message": f"Device discovery failed: {discovery_result.get('message')}"}
        
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
        request = xml_declaration.encode('utf-8') + ET.tostring(root, encoding='utf-8')
        
        # Send the command
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self._timeout)
        
        try:
            # Send the request
            sock.sendto(request, (self._ip, self._transponder_port))
            
            # Wait for response if acknowledgment was requested
            ack_requested = params and params.get("ack", "").lower() == "yes"
            
            if ack_requested:
                try:
                    data, _ = sock.recvfrom(4096)
                    
                    # Parse the response
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
            sock.close()
            
        # Default response for successful command
        return {
            "status": "sent", 
            "message": "Command sent successfully"
        }

    def set_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set audio processing mode.
        
        Args:
            mode: Audio processing mode name
            
        Returns:
            Command response
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Map mode to device identifier if needed
        device_mode = MODE_PRESETS.get(mode.lower(), mode)
        
        # Send the command
        return self.send_command("audioMode", {"value": device_mode})

    def set_input(self, input_source: str) -> Dict[str, Any]:
        """
        Set the input source.
        
        Args:
            input_source: Input source name or identifier
            
        Returns:
            Command response
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
            
        # Map input source to device identifier if needed
        device_input = INPUT_SOURCES.get(input_source.lower(), input_source)
        
        # Send the command
        return self.send_command("input", {"source": device_input})

    def set_source(self, source: str) -> Dict[str, Any]:
        """
        Set the source using the source command (alternative to input).
        
        Args:
            source: Source identifier
            
        Returns:
            Command response
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
            
        # Map source to device identifier if needed
        device_source = INPUT_SOURCES.get(source.lower(), source)
        
        # Send the command
        return self.send_command("source", {"value": device_source})

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

    def get_zone2_power(self) -> Dict[str, Any]:
        """
        Get the current Zone 2 power status.
        
        This method sends an update request for the zone2_power property,
        which will trigger a notification if subscribed.
        
        Returns:
            Dict[str, Any]: Update response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Send an update request for zone2_power
        update_data = {}
        
        # Create XML structure for update
        root = ET.Element("emotivaUpdate")
        root.set("protocol", PROTOCOL_VERSION)
        
        # Add zone2_power element
        ET.SubElement(root, "zone2_power")
        
        # Convert to XML string with XML declaration
        xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
        request = xml_declaration.encode('utf-8') + ET.tostring(root, encoding='utf-8')
        
        try:
            # Create socket for sending
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.settimeout(self._timeout)
            
            # Send request
            send_sock.sendto(request, (self._ip, self._transponder_port))
            send_sock.close()
            
            return {
                "status": "sent", 
                "message": "Zone 2 power update request sent. Current status will be delivered via notification."
            }
            
        except Exception as e:
            _LOGGER.error("Error sending Zone 2 power update request: %s", e)
            return {"status": "error", "message": str(e)}
    
    def set_zone2_power_on(self) -> Dict[str, Any]:
        """
        Turn on Zone 2 power.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Based on specification, use "value": "0" format, ensure acknowledgment
        return self.send_command("zone2_power_on", {"value": "0", "ack": "yes"})
    
    def set_zone2_power_off(self) -> Dict[str, Any]:
        """
        Turn off Zone 2 power.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Based on specification, use "value": "0" format, ensure acknowledgment
        return self.send_command("zone2_power_off", {"value": "0", "ack": "yes"})
    
    def toggle_zone2_power(self) -> Dict[str, Any]:
        """
        Toggle Zone 2 power state.
        
        Returns:
            Dict[str, Any]: Command response
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
        """
        # Based on specification, use "value": "0" format, ensure acknowledgment
        return self.send_command("zone2_power", {"value": "0", "ack": "yes"})

    def subscribe_to_notifications(self, event_types: Optional[List[str]] = None) -> Dict[str, Any]:
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
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": f"Device discovery failed: {discovery_result.get('message')}"}
        
        # Default to common notifications if not specified
        if not event_types:
            event_types = ["power", "zone2_power", "volume", "source", "audio_bitstream", "audio_bits", "video_input", "video_format"]
        
        # Create XML structure for subscription
        root = ET.Element("emotivaSubscription")
        root.set("protocol", PROTOCOL_VERSION)
        
        # Add property elements as per specification
        for event_type in event_types:
            # Handle common property aliases
            if event_type == "source":
                # "source" is likely "input" in NOTIFY_EVENTS
                if "input" in NOTIFY_EVENTS:
                    ET.SubElement(root, "input")
                else:
                    _LOGGER.warning("Cannot map 'source' to a known property")
            elif event_type in NOTIFY_EVENTS:
                ET.SubElement(root, event_type)
            else:
                _LOGGER.warning("Ignoring unknown notification event type: %s", event_type)
        
        # Convert to XML string with XML declaration
        xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
        request = xml_declaration.encode('utf-8') + ET.tostring(root, encoding='utf-8')
        
        try:
            # Create socket for sending
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.settimeout(self._timeout)
            
            # Send request
            send_sock.sendto(request, (self._ip, self._transponder_port))
            send_sock.close()
            
            # Don't wait for acknowledgment as the device may not send one
            # but will start sending notifications if subscription was successful
            _LOGGER.info("Subscription request sent to %s", self._ip)
            
            # Start notification listener if not already running
            if self._callback and not self._listener_thread:
                self._start_notification_listener()
            
            return {
                "status": "sent", 
                "message": "Subscription request sent. Subscription will be confirmed when notifications are received."
            }
            
        except Exception as e:
            _LOGGER.error("Error sending subscription request: %s", e)
            return {"status": "error", "message": str(e)}

    def __del__(self):
        """Clean up resources when the object is destroyed."""
        try:
            # Stop the notification listener if running
            self.stop_notification_listener()
        except Exception as e:
            _LOGGER.debug("Error during cleanup: %s", e)

    def _start_notification_listener(self) -> None:
        """Start a thread to listen for notifications from the device."""
        if self._listener_thread and self._listener_thread.is_alive():
            _LOGGER.debug("Notification listener already running for %s", self._ip)
            return
        
        # Create a socket to listen for notifications
        self._listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._listener_socket.settimeout(1.0)  # Short timeout to allow cleanup
        
        try:
            # Try to bind to the notification port
            self._listener_socket.bind(('', self._config.notify_port))
            _LOGGER.debug("Bound to notification port %d", self._config.notify_port)
        except OSError as e:
            _LOGGER.warning("Could not bind to notification port %d: %s. Using random port.", 
                           self._config.notify_port, e)
            self._listener_socket.bind(('', 0))
            used_port = self._listener_socket.getsockname()[1]
            _LOGGER.debug("Using port %d for notifications", used_port)
        
        # Flag to signal thread to stop
        self._listener_running = True
        
        # Start the listener thread
        self._listener_thread = threading.Thread(
            target=self._notification_listener_loop,
            daemon=True
        )
        self._listener_thread.start()
        _LOGGER.debug("Started notification listener thread for %s", self._ip)

    def _notification_listener_loop(self) -> None:
        """Main loop for the notification listener thread."""
        _LOGGER.debug("Notification listener started for %s", self._ip)
        
        while self._listener_running:
            try:
                # Wait for data with timeout
                data, addr = self._listener_socket.recvfrom(4096)
                if addr[0] == self._ip:
                    # Process the notification in the main thread to avoid threading issues
                    self._handle_notify(data)
            except socket.timeout:
                # This is expected, just continue
                pass
            except Exception as e:
                if self._listener_running:  # Only log if we're still supposed to be running
                    _LOGGER.error("Error in notification listener: %s", e)
        
        # Clean up
        try:
            self._listener_socket.close()
        except Exception as e:
            _LOGGER.error("Error closing listener socket: %s", e)
        
        _LOGGER.debug("Notification listener stopped for %s", self._ip)

    def stop_notification_listener(self) -> None:
        """Stop the notification listener thread."""
        if self._listener_thread and self._listener_thread.is_alive():
            _LOGGER.debug("Stopping notification listener for %s", self._ip)
            self._listener_running = False
            
            # Wait for the thread to exit
            self._listener_thread.join(timeout=2.0)
            if self._listener_thread.is_alive():
                _LOGGER.warning("Notification listener thread did not exit cleanly for %s", self._ip)
        
        self._listener_thread = None
        
    def update_properties(self, properties: List[str]) -> Dict[str, Any]:
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
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": f"Device discovery failed: {discovery_result.get('message')}"}
        
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
            # Create socket for sending
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.settimeout(self._timeout)
            
            # Send request
            send_sock.sendto(request, (self._ip, self._transponder_port))
            send_sock.close()
            
            return {
                "status": "sent", 
                "message": f"Update request sent for {len(mapped_properties)} properties. Current values will be delivered via notification."
            }
            
        except Exception as e:
            _LOGGER.error("Error sending update request: %s", e)
            return {"status": "error", "message": str(e)}

    def switch_to_hdmi(self, hdmi_number: int) -> Dict[str, Any]:
        """
        Switch to a specific HDMI source using commands from API spec section 4.1.
        
        This method tries multiple approaches to set both video and audio inputs 
        to the specified HDMI input:
        1. First tries the direct hdmiX command
        2. Then tries the source_X command
        3. Then tries setting source with hdmiX value
        
        Each attempt is followed by checking if both video and audio inputs changed.
        
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
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Subscribe to necessary notifications if not already subscribed
        self.subscribe_to_notifications(["audio_input", "video_input"])
        
        # Get the input name from our mappings
        input_id = f"hdmi{hdmi_number}"
        input_name = INPUT_SOURCES.get(input_id, f"HDMI {hdmi_number}")
        
        _LOGGER.debug("Attempting to set input to %s", input_name)
        
        # Method 1: Try direct hdmiX command
        _LOGGER.debug("Trying direct hdmi%d command", hdmi_number)
        result1 = self.send_command(f"hdmi{hdmi_number}", {"value": "0"})
        
        # Check if successful by requesting updates
        self.update_properties(["video_input", "audio_input"])
        time.sleep(2)  # Give time for notifications to arrive
        
        # Method 2: Try source_X command
        _LOGGER.debug("Trying source_%d command", hdmi_number)
        result2 = self.send_command(f"source_{hdmi_number}", {"value": "0"})
        
        # Check if successful by requesting updates
        self.update_properties(["video_input", "audio_input"])
        time.sleep(2)  # Give time for notifications to arrive
        
        # Method 3: Try source with hdmiX value
        _LOGGER.debug("Trying source with hdmi%d value", hdmi_number)
        result3 = self.send_command("source", {"value": f"hdmi{hdmi_number}"})
        
        # Check if successful by requesting updates
        self.update_properties(["video_input", "audio_input"])
        time.sleep(2)  # Give time for notifications to arrive
        
        # Method 4: Try separate video_input and audio_input commands
        _LOGGER.debug("Trying separate video_input and audio_input commands")
        video_result = self.send_command("video_input", {"value": f"hdmi{hdmi_number}"})
        time.sleep(1)
        audio_result = self.send_command("audio_input", {"value": f"hdmi{hdmi_number}"})
        
        # Final check
        self.update_properties(["video_input", "audio_input"])
        
        return {
            "status": "complete",
            "message": f"Attempted to switch to {input_name} using multiple methods",
            "attempts": [
                {"method": "hdmi_direct", "result": result1},
                {"method": "source_number", "result": result2},
                {"method": "source_value", "result": result3},
                {"method": "separate_inputs", "result": {"video": video_result, "audio": audio_result}}
            ]
        }
        
    def switch_to_source(self, source_command: str) -> Dict[str, Any]:
        """
        Switch to a specific source using commands from API spec section 4.1.
        
        This method accepts any of the source command strings listed in section 4.1
        of the API specification, such as:
        - source_tuner
        - source_1 through source_8
        - hdmi1 through hdmi8
        - coax1 through coax4
        - optical1 through optical4
        - analog1 through analog5
        - analog7.1
        - front_in
        - ARC
        - usb_stream
        - tuner
        
        Args:
            source_command (str): The source command from API spec section 4.1
                                 (e.g., "source_tuner", "hdmi1", "analog1", etc.)
            
        Returns:
            Dict[str, Any]: Command response with result status
            
        Raises:
            InvalidTransponderResponseError: If the device is not discovered or response is invalid
            InvalidSourceError: If an invalid source command is provided
        """
        # Check if discovery is complete
        if not self._discovery_complete:
            discovery_result = self.discover()
            if discovery_result.get("status") != "success":
                return {"status": "error", "message": "Device discovery failed"}
        
        # Subscribe to necessary notifications if not already subscribed
        self.subscribe_to_notifications(["audio_input", "video_input"])
        
        # Handle the HDMI special case - use our dedicated method
        if source_command.startswith("hdmi") and len(source_command) > 4:
            try:
                hdmi_number = int(source_command[4:])
                if 1 <= hdmi_number <= 8:
                    return self.switch_to_hdmi(hdmi_number)
            except ValueError:
                pass  # Not a valid hdmi number, continue with general approach
        
        # Handle source_X commands
        if source_command.startswith("source_"):
            # Check if it's a numbered source (source_1, source_2, etc.)
            if len(source_command) > 7 and source_command[7:].isdigit():
                source_num = source_command[7:]
                command = source_command
                value = "0"
            else:
                # For other source_ commands like source_tuner
                command = source_command
                value = "0"
        else:
            # For direct commands like analog1, tuner, etc.
            command = source_command
            value = "0"
        
        _LOGGER.debug("Switching to source using command: %s, value: %s", command, value)
        
        # Send the command
        result = self.send_command(command, {"value": value})
        
        # Request update to confirm the change
        self.update_properties(["video_input", "audio_input"])
        
        return {
            "status": "complete",
            "message": f"Attempted to switch to source using {command}",
            "result": result
        }
