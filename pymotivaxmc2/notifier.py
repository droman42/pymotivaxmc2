"""
UDP notification system for Emotiva devices.

This module provides a thread-based notification system that listens for UDP messages
from Emotiva devices and routes them to registered callbacks. It uses non-blocking
sockets and select() for efficient I/O handling.
"""

import socket
import select
import threading
import logging
from typing import Dict, Callable, Tuple, Any

_LOGGER = logging.getLogger(__name__)


class EmotivaNotifier(threading.Thread):
    """Thread-based UDP notification system for Emotiva devices.
    
    This class manages UDP sockets and routes incoming messages to registered callbacks.
    It runs as a daemon thread and uses non-blocking sockets with select() for efficient
    I/O handling.
    
    Attributes:
        _devs: Dictionary mapping IP addresses to their callback functions
        _socks_by_port: Dictionary mapping port numbers to their socket objects
        _socks_by_fileno: Dictionary mapping file descriptors to socket objects
        _lock: Thread lock for thread-safe operations
    """

    def __init__(self):
        """Initialize the EmotivaNotifier thread.
        
        Sets up the necessary dictionaries for device and socket management,
        and starts the thread as a daemon.
        """
        super().__init__()
        self._devs: Dict[str, Callable] = {}
        self._socks_by_port: Dict[int, socket.socket] = {}
        self._socks_by_fileno: Dict[int, socket.socket] = {}
        self._lock = threading.Lock()
        self.setDaemon(True)
        self.start()

    def register(self, ip: str, port: int, callback: Callable[[bytes], None]) -> None:
        """Register a device and its callback for notifications.
        
        Args:
            ip: IP address of the device to register
            port: UDP port to listen on for this device
            callback: Function to call when data is received from this device
        """
        with self._lock:
            if port not in self._socks_by_port:
                # Create and configure a new UDP socket for this port
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(('', port))
                sock.setblocking(0)  # Set non-blocking mode
                self._socks_by_port[port] = sock
                self._socks_by_fileno[sock.fileno()] = sock
            self._devs[ip] = callback

    def run(self) -> None:
        """Main thread loop that handles incoming UDP messages.
        
        Continuously monitors registered sockets for incoming data using select().
        When data is received, it looks up the appropriate callback and invokes it
        with the received data.
        """
        while True:
            if not self._socks_by_fileno:
                continue
            # Wait for any socket to become readable
            readable, _, _ = select.select(self._socks_by_fileno.values(), [], [])
            for sock in readable:
                # Receive data from the socket
                data, (ip, port) = sock.recvfrom(4096)
                _LOGGER.debug("Received data %s from %s:%d", data, ip, port)
                with self._lock:
                    cb = self._devs.get(ip)
                if cb:
                    cb(data)
