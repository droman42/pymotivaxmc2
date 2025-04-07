"""
Network communication utilities for the eMotiva integration.

This module provides network communication functionality for interacting with
Emotiva devices, including socket management and message handling.
"""

import socket
import select
import threading
import logging
from typing import Optional, Tuple, Callable
from .types import SocketDict, DeviceDict, DeviceCallback

_LOGGER = logging.getLogger(__name__)

class SocketManager(threading.Thread):
    """
    Thread-based socket manager for Emotiva devices.
    
    This class handles the creation, configuration, and cleanup of UDP sockets
    used for communication with Emotiva devices. It runs as a daemon thread
    to handle incoming messages asynchronously.
    """
    
    def __init__(self) -> None:
        """Initialize the socket manager thread."""
        super().__init__()
        self._sockets: SocketDict = {}
        self._devices: DeviceDict = {}
        self._lock = threading.Lock()
        self._running = True
        self.setDaemon(True)
        self.start()

    def create_socket(self, port: int) -> socket.socket:
        """
        Create and configure a new UDP socket.
        
        Args:
            port (int): Port number to bind the socket to
            
        Returns:
            socket.socket: Configured UDP socket
            
        Raises:
            socket.error: If socket creation or binding fails
        """
        _LOGGER.debug("Creating UDP socket for port %d", port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', port))
        sock.setblocking(0)
        return sock

    def register_device(self, ip: str, port: int, callback: DeviceCallback) -> None:
        """
        Register a device and its callback function.
        
        Args:
            ip (str): IP address of the device
            port (int): Port number to listen on
            callback (DeviceCallback): Function to call when data is received
        """
        with self._lock:
            if port not in self._sockets:
                try:
                    self._sockets[port] = self.create_socket(port)
                except socket.error as e:
                    _LOGGER.error("Failed to create socket for port %d: %s", port, e)
                    raise
            self._devices[ip] = callback
            _LOGGER.debug("Registered device %s on port %d", ip, port)

    def unregister_device(self, ip: str) -> None:
        """
        Unregister a device and clean up its socket if no longer needed.
        
        Args:
            ip (str): IP address of the device to unregister
        """
        with self._lock:
            if ip in self._devices:
                del self._devices[ip]
                _LOGGER.debug("Unregistered device %s", ip)
                
                # Clean up sockets that are no longer needed
                ports_to_remove = []
                for port, sock in self._sockets.items():
                    if not any(dev_ip != ip for dev_ip in self._devices):
                        sock.close()
                        ports_to_remove.append(port)
                
                for port in ports_to_remove:
                    del self._sockets[port]
                    _LOGGER.debug("Closed socket for port %d", port)

    def run(self) -> None:
        """Main thread loop for handling incoming messages."""
        while self._running:
            if not self._sockets:
                continue
                
            try:
                readable, _, _ = select.select(self._sockets.values(), [], [], 1.0)
                for sock in readable:
                    try:
                        data, (ip, port) = sock.recvfrom(4096)
                        _LOGGER.debug("Received data from %s:%d", ip, port)
                        
                        with self._lock:
                            callback = self._devices.get(ip)
                            if callback:
                                callback(data)
                    except socket.error as e:
                        _LOGGER.error("Error receiving data: %s", e)
            except select.error as e:
                _LOGGER.error("Error in select: %s", e)

    def send_data(self, ip: str, port: int, data: bytes) -> None:
        """
        Send data to a specific device.
        
        Args:
            ip (str): Destination IP address
            port (int): Destination port
            data (bytes): Data to send
            
        Raises:
            socket.error: If sending fails
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, (ip, port))
            _LOGGER.debug("Sent data to %s:%d", ip, port)
        except socket.error as e:
            _LOGGER.error("Failed to send data to %s:%d: %s", ip, port, e)
            raise
        finally:
            sock.close()

    def stop(self) -> None:
        """Stop the thread and clean up resources."""
        self._running = False
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up all sockets and device registrations."""
        with self._lock:
            for port, sock in self._sockets.items():
                try:
                    sock.close()
                    _LOGGER.debug("Closed socket for port %d", port)
                except socket.error as e:
                    _LOGGER.error("Error closing socket for port %d: %s", port, e)
            self._sockets.clear()
            self._devices.clear() 