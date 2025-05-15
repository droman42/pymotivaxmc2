"""
Network communication utilities for the Emotiva integration.

This module provides network communication functionality for interacting with
Emotiva devices, including socket management, device discovery, and connection monitoring.
"""

import socket
import asyncio
import logging
import time
import select
from typing import Optional, Dict, Callable, Set, Tuple, Any, List, TypeVar, Generic, Union, cast
from enum import Enum
from dataclasses import dataclass
from .emotiva_types import DeviceCallback
from .protocol import CommandFormatter, ResponseParser, ProtocolVersion, TransponderResponse
from .exceptions import (
    EmotivaNetworkError,
    CommandTimeoutError,
    DeviceOfflineError,
    InvalidResponseError
)

_LOGGER = logging.getLogger(__name__)

# Type variables for generics
T = TypeVar('T')
R = TypeVar('R')

class ConnectionState(str, Enum):
    """Connection states for Emotiva devices."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"

@dataclass
class NetworkDevice:
    """Information about a discovered device."""
    ip: str
    name: str
    model: str
    protocol_version: str
    ports: Dict[str, int]
    keepalive_interval: Optional[int] = None

class SocketManager:
    """
    Socket manager for Emotiva devices.
    
    This class handles the creation, configuration, and cleanup of UDP sockets
    used for communication with Emotiva devices.
    """
    
    def __init__(self, timeout: float = 2.0) -> None:
        """
        Initialize the socket manager.
        
        Args:
            timeout: Socket timeout in seconds
        """
        self._sockets: Dict[str, socket.socket] = {}  # IP:Port -> socket
        self._transports: Dict[int, asyncio.DatagramTransport] = {}  # Port -> transport
        self._protocols: Dict[int, Any] = {}  # Port -> protocol
        self._callbacks: Dict[str, DeviceCallback] = {}  # IP -> callback
        self._running_tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._timeout = timeout
        
    async def get_socket(self, host: str, port: int, socket_type: str = 'udp') -> socket.socket:
        """
        Get or create a socket for the specified host/port.
        
        Args:
            host: Destination hostname or IP
            port: Destination port
            socket_type: Socket type ('udp' or 'tcp')
            
        Returns:
            Socket instance
            
        Raises:
            ValueError: If socket_type is invalid
            OSError: If socket creation fails
        """
        socket_key = f"{host}:{port}:{socket_type}"
        
        async with self._lock:
            # Return existing socket if we have one
            if socket_key in self._sockets:
                return self._sockets[socket_key]
            
            # Create a new socket
            if socket_type == 'udp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            elif socket_type == 'tcp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                raise ValueError(f"Invalid socket type: {socket_type}")
            
            # Configure the socket
            sock.settimeout(self._timeout)
            
            # Store it
            self._sockets[socket_key] = sock
            _LOGGER.debug("Created new %s socket for %s:%d", socket_type, host, port)
            
            return sock

    async def close_socket(self, host: str, port: int, socket_type: str = 'udp') -> None:
        """
        Close a socket for the specified host/port.
        
        Args:
            host: Hostname or IP
            port: Port number
            socket_type: Socket type ('udp' or 'tcp')
        """
        socket_key = f"{host}:{port}:{socket_type}"
        
        async with self._lock:
            sock = self._sockets.pop(socket_key, None)
            if sock:
                try:
                    sock.close()
                    _LOGGER.debug("Closed %s socket for %s:%d", socket_type, host, port)
                except Exception as e:
                    _LOGGER.error("Error closing socket for %s:%d: %s", host, port, e)

    async def send_packet(self, host: str, port: int, data: bytes, socket_type: str = 'udp') -> None:
        """
        Send a packet to the specified host/port.
        
        Args:
            host: Destination hostname or IP
            port: Destination port
            data: Packet data to send
            socket_type: Socket type ('udp' or 'tcp')
            
        Raises:
            OSError: If sending fails
        """
        try:
            # Get or create a socket
            sock = await self.get_socket(host, port, socket_type)
            
            # Send the data
            if socket_type == 'udp':
                sock.sendto(data, (host, port))
            else:  # TCP
                sock.connect((host, port))
                sock.sendall(data)
                
            _LOGGER.debug("Sent %d bytes to %s:%d", len(data), host, port)
            
        except OSError as e:
            _LOGGER.error("Failed to send data to %s:%d: %s", host, port, e)
            raise
    
    async def receive_packet(self, host: str, port: int, 
                           socket_type: str = 'udp',
                           timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Receive a packet from the specified host/port.
        
        Args:
            host: Source hostname or IP
            port: Source port
            socket_type: Socket type ('udp' or 'tcp')
            timeout: Timeout in seconds, or None to use default
            
        Returns:
            Received packet data or None if timeout
            
        Raises:
            OSError: If receiving fails
        """
        try:
            # Get or create a socket
            sock = await self.get_socket(host, port, socket_type)
            
            # Set timeout if specified
            if timeout is not None:
                sock.settimeout(timeout)
            
            # Receive data
            if socket_type == 'udp':
                data, _ = sock.recvfrom(4096)
            else:  # TCP
                data = sock.recv(4096)
                
            _LOGGER.debug("Received %d bytes from %s:%d", len(data), host, port)
            return data
            
        except socket.timeout:
            _LOGGER.debug("Timeout receiving from %s:%d", host, port)
            return None
        except OSError as e:
            _LOGGER.error("Failed to receive data from %s:%d: %s", host, port, e)
            raise
    
    async def create_listening_socket(self, port: int, callback: Callable[[bytes, Tuple[str, int]], None]) -> None:
        """
        Create a socket to listen for incoming packets.
        
        Args:
            port: Port to listen on
            callback: Function to call when data is received
            
        Raises:
            OSError: If socket creation or binding fails
        """
        _LOGGER.debug("Creating listening socket for port %d", port)
        
        loop = asyncio.get_running_loop()
        
        # Define the protocol
        class UDPProtocol(asyncio.DatagramProtocol):
            def __init__(self, callback_func: Callable[[bytes, Tuple[str, int]], None]) -> None:
                self.callback = callback_func
                
            def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
                self.callback(data, addr)
                
            def connection_lost(self, exc: Optional[Exception]) -> None:
                _LOGGER.debug("Socket connection lost: %s", exc)
        
        # Create a transport
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: UDPProtocol(callback),
                local_addr=('', port)
            )
            
            async with self._lock:
                self._transports[port] = transport
                self._protocols[port] = protocol
                
            _LOGGER.debug("Created listening socket for port %d", port)
            
        except OSError as e:
            _LOGGER.error("Failed to create listening socket on port %d: %s", port, e)
            raise
    
    async def close_listening_socket(self, port: int) -> None:
        """
        Close a listening socket.
        
        Args:
            port: Port the socket is listening on
        """
        async with self._lock:
            transport = self._transports.pop(port, None)
            if transport:
                transport.close()
                _LOGGER.debug("Closed listening socket for port %d", port)
    
    async def register_device(self, ip: str, port: int, callback: DeviceCallback) -> None:
        """
        Register a device for callbacks when data is received.
        
        Args:
            ip: IP address of the device
            port: Port to listen on
            callback: Function to call when data is received
        """
        _LOGGER.debug("Registering device %s on port %d", ip, port)
        
        async with self._lock:
            # Store the callback
            self._callbacks[ip] = callback
            
            # Create a listening socket if needed
            if port not in self._transports:
                await self.create_listening_socket(
                    port, 
                    lambda data, addr: self._handle_received_data(data, addr)
                )
    
    async def unregister_device(self, ip: str) -> None:
        """
        Unregister a device and clean up resources.
        
        Args:
            ip: IP address of the device
        """
        _LOGGER.debug("Unregistering device %s", ip)
        
        async with self._lock:
            # Remove the callback
            self._callbacks.pop(ip, None)
            
            # Close any sockets specific to this device
            sockets_to_close = []
            for socket_key in self._sockets.keys():
                if socket_key.startswith(f"{ip}:"):
                    sockets_to_close.append(socket_key)
            
            for socket_key in sockets_to_close:
                sock = self._sockets.pop(socket_key)
                try:
                    sock.close()
                except Exception as e:
                    _LOGGER.error("Error closing socket for %s: %s", ip, e)
    
    def _handle_received_data(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        Handle data received from a device.
        
        Args:
            data: Received data
            addr: (IP, port) tuple of the sender
        """
        ip, port = addr
        _LOGGER.debug("Received %d bytes from %s:%d", len(data), ip, port)
        
        # Call the callback for this IP if registered
        callback = self._callbacks.get(ip)
        if callback:
            callback(ip, {"data": data, "port": port})
        else:
            _LOGGER.debug("No callback registered for %s", ip)
    
    async def cleanup(self) -> None:
        """Close all sockets and clean up resources."""
        _LOGGER.debug("Cleaning up SocketManager")
        
        async with self._lock:
            # Close all sockets
            for socket_key, sock in list(self._sockets.items()):
                try:
                    sock.close()
                except Exception as e:
                    _LOGGER.error("Error closing socket %s: %s", socket_key, e)
            
            # Close all transports
            for port, transport in list(self._transports.items()):
                try:
                    transport.close()
                except Exception as e:
                    _LOGGER.error("Error closing transport for port %d: %s", port, e)
            
            # Cancel all tasks
            for task in self._running_tasks:
                if not task.done():
                    task.cancel()
            
            if self._running_tasks:
                await asyncio.gather(*self._running_tasks, return_exceptions=True)
            
            # Clear collections
            self._sockets.clear()
            self._transports.clear()
            self._protocols.clear()
            self._callbacks.clear()
            self._running_tasks.clear()
            
        _LOGGER.debug("SocketManager cleanup complete")

class EmotivaNetworkDiscovery:
    """
    Class for discovering Emotiva devices on the network.
    
    This class handles device discovery using UDP broadcast messages.
    """
    
    def __init__(self, socket_manager: SocketManager, protocol_version: Optional[ProtocolVersion] = None) -> None:
        """
        Initialize the network discovery.
        
        Args:
            socket_manager: SocketManager instance for network operations
            protocol_version: Protocol version to use for discovery
        """
        self.socket_manager = socket_manager
        self.protocol_version = protocol_version or ProtocolVersion.latest()
        self._lock = asyncio.Lock()
    
    async def discover_devices(self, 
                             broadcast_addr: str = '255.255.255.255', 
                             port: int = 7000, 
                             timeout: float = 5.0,
                             attempts: int = 3) -> List[NetworkDevice]:
        """
        Discover Emotiva devices on the network.
        
        Args:
            broadcast_addr: Broadcast address
            port: Port to broadcast on
            timeout: Timeout in seconds
            attempts: Number of discovery attempts
            
        Returns:
            List of discovered devices
            
        Raises:
            OSError: If discovery fails
        """
        _LOGGER.debug("Starting device discovery (broadcast=%s, port=%d)", broadcast_addr, port)
        
        # Create a temporary socket for receiving responses
        resp_port = 57000  # Use a high port number that's likely free
        devices: Dict[str, NetworkDevice] = {}
        
        # Create a temporary socket with broadcast capability
        broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        broadcast_sock.settimeout(timeout / attempts)  # Split timeout between attempts
        
        try:
            # Create a temporary receive socket
            resp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            resp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            resp_sock.bind(('', resp_port))
            resp_sock.settimeout(timeout / attempts)
            
            # Format the discovery request
            protocol_version = self.protocol_version
            if isinstance(protocol_version, ProtocolVersion):
                protocol_version = ProtocolVersion.latest()
            discovery_req = CommandFormatter.format_ping_request(protocol_version)
            
            # Make multiple attempts
            for attempt in range(attempts):
                _LOGGER.debug("Discovery attempt %d of %d", attempt + 1, attempts)
                
                try:
                    # Send the discovery request
                    broadcast_sock.sendto(discovery_req, (broadcast_addr, port))
                    
                    # Listen for responses
                    start_time = time.time()
                    while time.time() - start_time < (timeout / attempts):
                        try:
                            # Check if the socket is ready to read
                            ready = select.select([resp_sock], [], [], 0.1)
                            if not ready[0]:
                                continue
                                
                            # Receive the data
                            data, addr = resp_sock.recvfrom(4096)
                            sender_ip = addr[0]
                            
                            _LOGGER.debug("Received discovery response from %s", sender_ip)
                            
                            # Parse the response
                            response_doc = ResponseParser.parse_response(data)
                            if response_doc is None:
                                _LOGGER.warning("Invalid discovery response from %s", sender_ip)
                                continue
                                
                            transponder = ResponseParser.parse_transponder_response(response_doc)
                            if transponder is None:
                                _LOGGER.warning("Invalid transponder response from %s", sender_ip)
                                continue
                                
                            # Create a device entry
                            device = NetworkDevice(
                                ip=sender_ip,
                                name=transponder.name,
                                model=transponder.model,
                                protocol_version=transponder.version,
                                ports=transponder.ports,
                                keepalive_interval=transponder.keepalive_interval
                            )
                            
                            # Add to discovered devices
                            devices[sender_ip] = device
                            _LOGGER.info("Discovered device: %s (%s) at %s", 
                                       device.name, device.model, device.ip)
                            
                        except socket.timeout:
                            # Timeout is expected, just continue
                            pass
                        except Exception as e:
                            _LOGGER.error("Error processing discovery response: %s", e)
                
                except Exception as e:
                    _LOGGER.error("Error in discovery attempt %d: %s", attempt + 1, e)
            
            return list(devices.values())
            
        finally:
            # Clean up the temporary sockets
            try:
                broadcast_sock.close()
            except:
                pass
                
            try:
                resp_sock.close()
            except:
                pass

class BroadcastListener:
    """
    Listener for device broadcast announcements.
    
    This class listens for UDP broadcasts from Emotiva devices announcing their presence.
    """
    
    def __init__(self, socket_manager: SocketManager) -> None:
        """
        Initialize the broadcast listener.
        
        Args:
            socket_manager: SocketManager instance for network operations
        """
        self.socket_manager = socket_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[NetworkDevice], None]] = []
        self._port = 7000  # Default port for device announcements
        self._lock = asyncio.Lock()
    
    async def start(self, port: int = 7000) -> None:
        """
        Start listening for broadcasts.
        
        Args:
            port: Port to listen on
            
        Raises:
            OSError: If starting the listener fails
        """
        async with self._lock:
            if self._running:
                return
                
            _LOGGER.debug("Starting broadcast listener on port %d", port)
            self._port = port
            
            # Create a listening socket
            try:
                def broadcast_callback(data: bytes, addr: Tuple[str, int]) -> None:
                    # We need to use a non-async callback here
                    # and then create the task manually
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._handle_broadcast(data, addr))
                
                await self.socket_manager.create_listening_socket(port, broadcast_callback)
                
                self._running = True
                _LOGGER.info("Broadcast listener started on port %d", port)
                
            except OSError as e:
                _LOGGER.error("Failed to start broadcast listener: %s", e)
                raise
    
    async def stop(self) -> None:
        """Stop listening for broadcasts."""
        async with self._lock:
            if not self._running:
                return
                
            _LOGGER.debug("Stopping broadcast listener")
            
            # Close the listening socket
            if self._port is not None:
                await self.socket_manager.close_listening_socket(self._port)
                
            self._running = False
            _LOGGER.info("Broadcast listener stopped")
    
    async def _handle_broadcast(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        Handle a received broadcast.
        
        Args:
            data: Received data
            addr: (IP, port) tuple of the sender
        """
        sender_ip, sender_port = addr
        _LOGGER.debug("Received broadcast from %s:%d", sender_ip, sender_port)
        
        try:
            # Parse the response
            response_doc = ResponseParser.parse_response(data)
            if response_doc is None:
                _LOGGER.warning("Invalid broadcast from %s", sender_ip)
                return
                
            transponder = ResponseParser.parse_transponder_response(response_doc)
            if transponder is None:
                _LOGGER.warning("Invalid transponder broadcast from %s", sender_ip)
                return
                
            # Create a device entry
            device = NetworkDevice(
                ip=sender_ip,
                name=transponder.name,
                model=transponder.model,
                protocol_version=transponder.version,
                ports=transponder.ports,
                keepalive_interval=transponder.keepalive_interval
            )
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(device)
                except Exception as e:
                    _LOGGER.error("Error in broadcast callback: %s", e)
                    
        except Exception as e:
            _LOGGER.error("Error processing broadcast from %s: %s", sender_ip, e)
    
    def register_callback(self, callback: Callable[[NetworkDevice], None]) -> None:
        """
        Register a callback for device broadcasts.
        
        Args:
            callback: Function to call when a device is discovered
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            _LOGGER.debug("Registered broadcast callback")
    
    def unregister_callback(self, callback: Callable[[NetworkDevice], None]) -> None:
        """
        Unregister a callback.
        
        Args:
            callback: Function to unregister
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            _LOGGER.debug("Unregistered broadcast callback")

class ConnectionManager:
    """
    Manages device connections and monitoring.
    
    This class tracks device connection states and handles reconnection.
    """
    
    def __init__(self, socket_manager: SocketManager) -> None:
        """
        Initialize the connection manager.
        
        Args:
            socket_manager: SocketManager instance for network operations
        """
        self.socket_manager = socket_manager
        self._connection_states: Dict[str, ConnectionState] = {}
        self._callbacks: Dict[str, List[Callable[[str, ConnectionState], None]]] = {}
        self._last_activity: Dict[str, float] = {}
        self._keepalive_intervals: Dict[str, int] = {}
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
    
    async def register_device(self, ip: str, keepalive_interval: int = 30000) -> None:
        """
        Register a device for connection monitoring.
        
        Args:
            ip: IP address of the device
            keepalive_interval: Keepalive interval in milliseconds
        """
        async with self._lock:
            # Store the keepalive interval
            self._keepalive_intervals[ip] = keepalive_interval
            
            # Initialize connection state
            if ip not in self._connection_states:
                self._connection_states[ip] = ConnectionState.DISCONNECTED
                self._last_activity[ip] = time.time()
                
                # Start monitoring
                self._start_monitoring(ip)
    
    async def unregister_device(self, ip: str) -> None:
        """
        Unregister a device.
        
        Args:
            ip: IP address of the device
        """
        async with self._lock:
            # Stop monitoring
            if ip in self._monitoring_tasks:
                task = self._monitoring_tasks.pop(ip)
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            
            # Remove from state tracking
            self._connection_states.pop(ip, None)
            self._last_activity.pop(ip, None)
            self._keepalive_intervals.pop(ip, None)
            self._callbacks.pop(ip, None)
    
    def _start_monitoring(self, ip: str) -> None:
        """
        Start monitoring a device's connection.
        
        Args:
            ip: IP address of the device
        """
        if ip in self._monitoring_tasks and not self._monitoring_tasks[ip].done():
            return
            
        task = asyncio.create_task(self._monitor_connection(ip))
        self._monitoring_tasks[ip] = task
        _LOGGER.debug("Started connection monitoring for %s", ip)
    
    async def _monitor_connection(self, ip: str) -> None:
        """
        Monitor a device's connection state.
        
        Args:
            ip: IP address of the device
        """
        try:
            while ip in self._connection_states:
                # Get the current state
                state = self._connection_states[ip]
                
                # Check last activity time
                now = time.time()
                last_activity = self._last_activity.get(ip, 0)
                keepalive_interval = self._keepalive_intervals.get(ip, 30000) / 1000  # Convert to seconds
                
                # If we're connected or connecting, check if we've timed out
                if state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
                    # Allow 1.5x the keepalive interval before considering disconnected
                    if now - last_activity > keepalive_interval * 1.5:
                        _LOGGER.warning("Device %s timed out (no activity for %.1f seconds)", 
                                       ip, now - last_activity)
                        await self._set_connection_state(ip, ConnectionState.DISCONNECTED)
                
                # Sleep before checking again (1/4 of the keepalive interval)
                await asyncio.sleep(max(1, keepalive_interval / 4))
                
        except asyncio.CancelledError:
            _LOGGER.debug("Connection monitoring for %s cancelled", ip)
            
        except Exception as e:
            _LOGGER.error("Error in connection monitoring for %s: %s", ip, e)
    
    async def update_activity(self, ip: str) -> None:
        """
        Update the last activity time for a device.
        
        Args:
            ip: IP address of the device
        """
        if ip in self._last_activity:
            self._last_activity[ip] = time.time()
            
            # If we're not connected, update the state
            if self._connection_states.get(ip) != ConnectionState.CONNECTED:
                await self._set_connection_state(ip, ConnectionState.CONNECTED)
    
    async def _set_connection_state(self, ip: str, state: ConnectionState) -> None:
        """
        Set the connection state for a device.
        
        Args:
            ip: IP address of the device
            state: New connection state
        """
        async with self._lock:
            if ip not in self._connection_states or self._connection_states[ip] == state:
                return
                
            # Update the state
            old_state = self._connection_states[ip]
            self._connection_states[ip] = state
            
            _LOGGER.info("Device %s connection state changed: %s -> %s", ip, old_state, state)
            
            # Notify callbacks
            if ip in self._callbacks:
                for callback in self._callbacks[ip]:
                    try:
                        callback(ip, state)
                    except Exception as e:
                        _LOGGER.error("Error in connection state callback: %s", e)
    
    async def register_callback(self, ip: str, callback: Callable[[str, ConnectionState], None]) -> None:
        """
        Register a callback for connection state changes.
        
        Args:
            ip: IP address of the device
            callback: Function to call when state changes
        """
        async with self._lock:
            if ip not in self._callbacks:
                self._callbacks[ip] = []
                
            if callback not in self._callbacks[ip]:
                self._callbacks[ip].append(callback)
                
                # Call immediately with current state
                if ip in self._connection_states:
                    callback(ip, self._connection_states[ip])
    
    async def unregister_callback(self, ip: str, callback: Callable[[str, ConnectionState], None]) -> None:
        """
        Unregister a connection state callback.
        
        Args:
            ip: IP address of the device
            callback: Function to unregister
        """
        async with self._lock:
            if ip in self._callbacks and callback in self._callbacks[ip]:
                self._callbacks[ip].remove(callback)
                
                # Clean up if this was the last callback
                if not self._callbacks[ip]:
                    self._callbacks.pop(ip, None)
    
    def get_connection_state(self, ip: str) -> ConnectionState:
        """
        Get the current connection state for a device.
        
        Args:
            ip: IP address of the device
            
        Returns:
            Current connection state
        """
        return self._connection_states.get(ip, ConnectionState.DISCONNECTED)
    
    async def cleanup(self) -> None:
        """Clean up resources and stop monitoring."""
        _LOGGER.debug("Cleaning up ConnectionManager")
        
        async with self._lock:
            # Cancel all monitoring tasks
            for ip, task in list(self._monitoring_tasks.items()):
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete
            if self._monitoring_tasks:
                await asyncio.gather(*self._monitoring_tasks.values(), return_exceptions=True)
            
            # Clear collections
            self._connection_states.clear()
            self._callbacks.clear()
            self._last_activity.clear()
            self._keepalive_intervals.clear()
            self._monitoring_tasks.clear()
            
        _LOGGER.debug("ConnectionManager cleanup complete")

class CommandExecutor:
    """
    Executes commands on Emotiva devices.
    
    This class handles command execution, retries, and error handling.
    """
    
    def __init__(self, socket_manager: SocketManager) -> None:
        """
        Initialize the command executor.
        
        Args:
            socket_manager: SocketManager instance for network operations
        """
        self.socket_manager = socket_manager
        self._lock = asyncio.Lock()
    
    async def execute_command(self, 
                            ip: str, 
                            port: int, 
                            data: bytes, 
                            retries: int = 3, 
                            timeout: float = 2.0) -> Optional[bytes]:
        """
        Execute a command on a device.
        
        Args:
            ip: IP address of the device
            port: Port to send to
            data: Command data to send
            retries: Number of retry attempts
            timeout: Timeout in seconds for each attempt
            
        Returns:
            Response data or None if no response received
            
        Raises:
            OSError: If command execution fails after retries
        """
        last_error = None
        
        for attempt in range(retries):
            try:
                # Send the command
                await self.socket_manager.send_packet(ip, port, data)
                
                # Wait for a response
                response = await self.socket_manager.receive_packet(ip, port, timeout=timeout)
                if response:
                    return response
                
                _LOGGER.warning("No response from %s on attempt %d of %d", ip, attempt + 1, retries)
                
            except OSError as e:
                _LOGGER.warning("Error sending command to %s on attempt %d: %s", ip, attempt + 1, e)
                last_error = e
                
            # Wait before retrying (exponential backoff)
            if attempt < retries - 1:
                await asyncio.sleep(0.1 * (2 ** attempt))
        
        # If we get here, all retries failed
        if last_error:
            _LOGGER.error("Command execution failed after %d attempts: %s", retries, last_error)
            raise last_error
            
        return None 