"""Async socket manager that owns the small fixed set of UDP ports."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Dict, Tuple, Awaitable

from .logging import get_logger, log_xml

# Module logger
_LOGGER = get_logger("socket_mgr")

class _DatagramProto(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue[Tuple[bytes, Tuple[str, int]]]):
        self.queue = queue
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.queue.put_nowait((data, addr))

    def error_received(self, exc):
        # Log the error but don't propagate it
        _LOGGER.warning("Socket error received: %s", exc)
        # Upper layer handles timeouts etc.
        pass

    def connection_lost(self, exc):
        if exc:
            _LOGGER.warning("Connection lost due to error: %s", exc)
        else:
            _LOGGER.debug("Connection closed cleanly")

class SocketManager:
    """Binds and maintains the required UDP ports for a single device."""

    def __init__(self, device_host: str, ports: Dict[str, int]):
        self.device_host = device_host
        self.ports = ports
        self._loop = asyncio.get_running_loop()
        self._queues: Dict[int, asyncio.Queue] = {}
        self._transports: Dict[int, asyncio.DatagramTransport] = {}
        
        # Phase 1 Fix: Add port binding synchronization
        self._start_lock = asyncio.Lock()
        
        _LOGGER.info("SocketManager initialized for device %s with ports %s", device_host, ports)

    async def start(self):
        """Start socket manager with port binding protection."""
        # Phase 1 Fix: Protect against concurrent start() calls
        async with self._start_lock:
            _LOGGER.debug("Starting socket manager for %s", self.device_host)
            for name, port in self.ports.items():
                if port in self._transports:
                    _LOGGER.debug("Port %d already bound for %s", port, name)
                    continue
                
                _LOGGER.debug("Binding to port %d for %s", port, name)
                queue: asyncio.Queue = asyncio.Queue()
                try:
                    transport, _ = await self._loop.create_datagram_endpoint(
                        lambda: _DatagramProto(queue),
                        local_addr=("0.0.0.0", port),
                    )
                    self._queues[port] = queue
                    self._transports[port] = transport
                    _LOGGER.info("Successfully bound to port %d for %s", port, name)
                except OSError as e:
                    _LOGGER.error("Failed to bind to port %d for %s: %s", port, name, e)
                    # Phase 1 Fix: Clean up partial state on failure
                    await self._cleanup_partial_state()
                    raise

    async def _cleanup_partial_state(self):
        """Clean up any partially created transports."""
        for port, transport in list(self._transports.items()):
            try:
                transport.close()
                _LOGGER.debug("Cleaned up transport for port %d", port)
            except Exception as e:
                _LOGGER.warning("Error cleaning up transport for port %d: %s", port, e)
        self._transports.clear()
        self._queues.clear()

    async def stop(self):
        """Stop socket manager with proper cleanup."""
        # Phase 1 Fix: Use same lock for stop to ensure consistency
        async with self._start_lock:
            _LOGGER.debug("Stopping socket manager")
            for port, t in self._transports.items():
                _LOGGER.debug("Closing transport for port %d", port)
                t.close()
            self._transports.clear()
            _LOGGER.info("Socket manager stopped")

    async def send(self, payload: bytes, port_name: str = "controlPort"):
        port = self.ports[port_name]
        transport = self._transports[port]
        _LOGGER.debug("Sending %d bytes to %s:%d (%s)", len(payload), self.device_host, port, port_name)
        log_xml(_LOGGER, "sent", payload)
        transport.sendto(payload, (self.device_host, port))

    async def recv(self, port_name: str, timeout: float | None = None):
        port = self.ports[port_name]
        queue = self._queues[port]
        try:
            data, addr = await asyncio.wait_for(queue.get(), timeout=timeout)
            _LOGGER.debug("Received %d bytes from %s:%d on port %s", len(data), addr[0], addr[1], port_name)
            log_xml(_LOGGER, "received", data)
            return data, addr
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout waiting for data on port %s after %.1f seconds", port_name, timeout)
            raise
