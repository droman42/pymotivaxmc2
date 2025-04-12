"""
Network communication utilities for the eMotiva integration.

This module provides network communication functionality for interacting with
Emotiva devices, including socket management and message handling.
"""

import socket
import asyncio
import logging
from typing import Optional, Dict, Callable, Set
from .types import DeviceCallback

_LOGGER = logging.getLogger(__name__)

class AsyncSocketManager:
    """
    Asyncio-based socket manager for Emotiva devices.
    
    This class handles the creation, configuration, and cleanup of UDP sockets
    used for communication with Emotiva devices using asyncio for asynchronous I/O.
    """
    
    def __init__(self) -> None:
        """Initialize the socket manager."""
        self._transports: Dict[int, asyncio.DatagramTransport] = {}
        self._protocols: Dict[int, asyncio.DatagramProtocol] = {}
        self._devices: Dict[str, DeviceCallback] = {}
        self._running_tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        
    async def create_socket(self, port: int, callback: Callable[[bytes, tuple], None]) -> None:
        """
        Create and configure a new UDP socket using asyncio.
        
        Args:
            port: Port number to bind the socket to
            callback: Function to call when data is received
            
        Raises:
            OSError: If socket creation or binding fails
        """
        _LOGGER.debug("Creating UDP socket for port %d", port)
        
        class UDPProtocol(asyncio.DatagramProtocol):
            def __init__(self, callback_func):
                self.callback = callback_func
                
            def datagram_received(self, data, addr):
                self.callback(data, addr)
                
            def connection_lost(self, exc):
                _LOGGER.debug("Socket connection lost: %s", exc)
        
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(callback),
            local_addr=('', port)
        )
        
        self._transports[port] = transport
        self._protocols[port] = protocol

    async def register_device(self, ip: str, port: int, callback: DeviceCallback) -> None:
        """
        Register a device and its callback function.
        
        Args:
            ip: IP address of the device
            port: Port number to listen on
            callback: Function to call when data is received
        """
        async with self._lock:
            if port not in self._transports:
                try:
                    await self.create_socket(
                        port,
                        lambda data, addr: self._handle_data(data, addr)
                    )
                except OSError as e:
                    _LOGGER.error("Failed to create socket for port %d: %s", port, e)
                    raise
            self._devices[ip] = callback
            _LOGGER.debug("Registered device %s on port %d", ip, port)

    async def unregister_device(self, ip: str) -> None:
        """
        Unregister a device and clean up its socket if no longer needed.
        
        Args:
            ip: IP address of the device to unregister
        """
        async with self._lock:
            if ip in self._devices:
                del self._devices[ip]
                _LOGGER.debug("Unregistered device %s", ip)
                
                # Clean up ports that are no longer needed
                ports_to_remove = []
                for port in self._transports:
                    # Check if any device still uses this port
                    if not any(d_ip != ip for d_ip in self._devices):
                        ports_to_remove.append(port)
                
                for port in ports_to_remove:
                    transport = self._transports.pop(port, None)
                    if transport:
                        transport.close()
                    _LOGGER.debug("Closed socket for port %d", port)

    def _handle_data(self, data: bytes, addr: tuple) -> None:
        """
        Handle incoming data from a socket.
        
        Args:
            data: Received data
            addr: (IP, port) tuple of the sender
        """
        ip, port = addr
        _LOGGER.debug("Received data from %s:%d", ip, port)
        
        callback = self._devices.get(ip)
        if callback:
            callback(data)

    async def send_data(self, ip: str, port: int, data: bytes) -> None:
        """
        Send data to a specific device asynchronously.
        
        Args:
            ip: Destination IP address
            port: Destination port
            data: Data to send
            
        Raises:
            OSError: If sending fails
        """
        try:
            # Create a temporary transport for sending
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                asyncio.DatagramProtocol,
                remote_addr=(ip, port)
            )
            
            try:
                transport.sendto(data)
                _LOGGER.debug("Sent data to %s:%d", ip, port)
            finally:
                transport.close()
                
        except OSError as e:
            _LOGGER.error("Failed to send data to %s:%d: %s", ip, port, e)
            raise

    async def cleanup(self) -> None:
        """Clean up all sockets and device registrations."""
        async with self._lock:
            for port, transport in self._transports.items():
                try:
                    transport.close()
                    _LOGGER.debug("Closed socket for port %d", port)
                except Exception as e:
                    _LOGGER.error("Error closing socket for port %d: %s", port, e)
            
            # Clear collections
            self._transports.clear()
            self._protocols.clear()
            self._devices.clear()
            
            # Cancel any running tasks
            for task in self._running_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete/cancel
            if self._running_tasks:
                await asyncio.gather(*self._running_tasks, return_exceptions=True)
            self._running_tasks.clear() 