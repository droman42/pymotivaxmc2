"""
UDP notification system for Emotiva devices.

This module provides an asyncio-based notification system that listens for UDP messages
from Emotiva devices and routes them to registered callbacks. It uses asyncio for
efficient asynchronous I/O handling.
"""

import socket
import asyncio
import logging
import ipaddress
from typing import Dict, Callable, Set, Optional, List

_LOGGER = logging.getLogger(__name__)

class AsyncEmotivaNotifier:
    """Asyncio-based UDP notification system for Emotiva devices.
    
    This class manages UDP sockets and routes incoming messages to registered callbacks.
    It uses asyncio for efficient, non-blocking I/O operations.
    
    Attributes:
        _devices: Dictionary mapping IP addresses to their callback functions
        _socket: Socket object for notifications
        _task: Asyncio task for notification listener
        _lock: Asyncio lock for thread-safe operations
        _running: Flag to control listener task
    """

    def __init__(self):
        """Initialize the AsyncEmotivaNotifier."""
        self._devices: Dict[str, Callable] = {}
        self._socket: Optional[socket.socket] = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._running = False
        self._port = None
        self._is_cleaning_up = False

    async def register(self, ip: str, port: int, callback: Callable[[bytes], None]) -> None:
        """Register a device and its callback for notifications.
        
        Args:
            ip: IP address of the device to register
            port: UDP port to listen on for this device
            callback: Function to call when data is received from this device
        """
        # Don't allow registration during cleanup
        if self._is_cleaning_up:
            _LOGGER.warning("Cannot register device during cleanup")
            return
            
        async with self._lock:
            # Validate that the IP address format is valid
            try:
                socket.inet_aton(ip)
                _LOGGER.debug("IP address %s validated", ip)
            except OSError:
                _LOGGER.error("Invalid IP address format: %s", ip)
                raise
            
            # Create socket if it doesn't exist or if port has changed
            if self._socket is None or (self._port is not None and self._port != port):
                # Close existing socket if any
                if self._socket is not None:
                    self._socket.close()
                    self._socket = None
                
                # Create new socket
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socket.setblocking(False)
                
                try:
                    # Try to bind to any interface on the port
                    self._socket.bind(('', port))
                    self._port = port
                    _LOGGER.debug("Bound socket to all interfaces on port %d", port)
                except OSError as e:
                    _LOGGER.warning("Could not bind to all interfaces: %s. Trying localhost...", e)
                    try:
                        # Try to bind to localhost only
                        self._socket.bind(('127.0.0.1', port))
                        self._port = port
                        _LOGGER.warning("Bound socket to localhost only on port %d. Notifications may not work correctly.", port)
                    except OSError as e2:
                        _LOGGER.error("Failed to bind socket: %s", e2)
                        self._socket.close()
                        self._socket = None
                        raise RuntimeError(f"Cannot create notification listener on port {port}")
            
            # Start listener task if not already running
            if not self._running and self._socket is not None:
                self._running = True
                self._task = asyncio.create_task(self._notification_listener())
                self._task.add_done_callback(self._on_task_done)
                _LOGGER.debug("Started notification listener task")
            
            # Register the device callback
            self._devices[ip] = callback
            _LOGGER.debug("Registered device %s for notifications", ip)
    
    def _on_task_done(self, task):
        """Callback for when the notification task completes."""
        try:
            # Check if the task raised an exception
            exc = task.exception()
            if exc:
                _LOGGER.error("Notification listener task failed with exception: %s", exc)
            else:
                _LOGGER.debug("Notification listener task completed normally")
        except asyncio.CancelledError:
            _LOGGER.debug("Notification listener task was cancelled")
        except Exception as e:
            _LOGGER.error("Error handling notification task completion: %s", e)

    async def _notification_listener(self) -> None:
        """Background task to handle incoming notifications."""
        _LOGGER.debug("Notification listener started")
        
        loop = asyncio.get_running_loop()
        
        while self._running and self._socket is not None:
            try:
                # Use asyncio to wait for data
                data, addr = await loop.sock_recvfrom(self._socket, 4096)
                ip_addr, _ = addr
                
                _LOGGER.debug("Received %d bytes from %s", len(data), ip_addr)
                
                # Find the right callback
                for device_ip, callback in self._devices.items():
                    try:
                        if device_ip == ip_addr or socket.inet_aton(device_ip) == socket.inet_aton(ip_addr):
                            try:
                                callback(data)
                            except Exception as e:
                                _LOGGER.error("Error in notification callback: %s", e)
                            break
                    except OSError:
                        # In case of IP address format error, just do a string comparison
                        if device_ip == ip_addr:
                            try:
                                callback(data)
                            except Exception as e:
                                _LOGGER.error("Error in notification callback: %s", e)
                            break
                else:
                    _LOGGER.warning("Received notification from unknown device: %s", ip_addr)
            except asyncio.CancelledError:
                _LOGGER.debug("Notification listener task cancelled")
                break
            except Exception as e:
                if self._running:  # Only log if we're still supposed to be running
                    _LOGGER.error("Error in notification listener: %s", e)
                await asyncio.sleep(0.1)
                
        _LOGGER.debug("Notification listener stopped")

    async def unregister(self, ip: str) -> None:
        """Unregister a device from notifications.
        
        Args:
            ip: IP address of the device to unregister
        """
        # Don't allow unregistration during cleanup
        if self._is_cleaning_up:
            return
            
        async with self._lock:
            if ip in self._devices:
                del self._devices[ip]
                _LOGGER.debug("Unregistered device %s", ip)
                
                # If no more devices, stop the listener
                if not self._devices:
                    await self.cleanup()

    async def force_stop_listener(self):
        """Force the listener task to stop immediately without acquiring the lock."""
        # Mark that we're running
        self._running = False
        
        # Cancel the task if it exists
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                # Wait for a very short time for the task to cancel
                await asyncio.wait_for(asyncio.shield(self._task), timeout=0.5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # This is expected
                pass
            except Exception as e:
                _LOGGER.error("Error waiting for task cancellation: %s", e)
                
    async def cleanup(self) -> None:
        """Clean up all resources used by the notifier."""
        # Prevent multiple cleanup calls
        if self._is_cleaning_up:
            return
            
        self._is_cleaning_up = True
        
        try:
            # First try to get the lock, but don't wait too long
            try:
                lock_acquired = False
                lock_acquired = await asyncio.wait_for(self._lock.acquire(), timeout=1.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Could not acquire lock for cleanup, performing forced cleanup")
            
            try:
                # Stop the listener
                self._running = False
                
                # Cancel the task
                if self._task is not None:
                    if not self._task.done():
                        self._task.cancel()
                        try:
                            # Wait briefly for the task to cancel
                            await asyncio.wait_for(asyncio.shield(self._task), timeout=0.5)
                        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                            # These exceptions are expected
                            pass
                    self._task = None
                
                # Close the socket
                if self._socket is not None:
                    try:
                        self._socket.close()
                        _LOGGER.debug("Closed notification socket for port %d", self._port)
                    except Exception as e:
                        _LOGGER.error("Error closing notification socket: %s", e)
                    self._socket = None
                    self._port = None
                
                # Clear device map
                self._devices.clear()
            finally:
                # Release the lock if we acquired it
                if lock_acquired:
                    self._lock.release()
        finally:
            self._is_cleaning_up = False
