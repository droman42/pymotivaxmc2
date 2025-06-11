"""High‑level facade for Emotiva devices (v0.2.0)."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Callable, Awaitable, Dict, Any, Sequence, List
from .core.discovery import Discovery
from .core.socket_mgr import SocketManager
from .core.protocol import Protocol
from .core.dispatcher import Dispatcher
from .core.xmlcodec import build_subscribe, build_unsubscribe
from .core.logging import get_logger, setup_logging
from .enums import Command, Property, Input, Zone
from .exceptions import EmotivaError, AckTimeoutError, InvalidArgumentError

# Module logger
_LOGGER = get_logger("controller")

class EmotivaController:
    """Async facade for Emotiva devices.

    Args:
        host: IP or hostname of device.
        timeout: Discovery timeout seconds.
        protocol_max: Maximum protocol version to use.
    """
    def __init__(self, host: str, *, timeout: float = 5.0, protocol_max: str = "3.1"):
        self.host = host
        self.timeout = timeout
        self.protocol_max = protocol_max
        self._info: Dict[str, Any] | None = None
        self._socket_mgr: SocketManager | None = None
        self._protocol: Protocol | None = None
        self._dispatcher: Dispatcher | None = None
        
        # Phase 1 Fix: Add connection state protection
        self._connection_lock = asyncio.Lock()
        self._connected = False
        
        _LOGGER.info("Initialized controller for device at %s (timeout=%.1f)", host, timeout)

    # ---------- connection -------------------------------------------------
    async def connect(self):
        """Discover device, bind sockets, start dispatcher."""
        # Phase 1 Fix: Protect against concurrent connect() calls
        async with self._connection_lock:
            if self._connected:
                _LOGGER.debug("Already connected to device at %s", self.host)
                return
                
            _LOGGER.info("Connecting to device at %s", self.host)
            disc = Discovery(self.host, timeout=self.timeout)
            try:
                self._info = await disc.fetch_transponder()
                _LOGGER.debug("Device transponder info: %s", self._info)
            except Exception as e:
                _LOGGER.error("Failed to discover device: %s", e)
                raise

            # Get protocol version from discovery response
            device_protocol_version = self._info.get("protocolVersion", "2.0")
            
            # Use the lower of the device's supported version and our max supported version
            if self.protocol_max < device_protocol_version:
                protocol_version = self.protocol_max
                _LOGGER.info("Device supports protocol %s but we're limiting to %s", 
                           device_protocol_version, protocol_version)
            else:
                protocol_version = device_protocol_version
                _LOGGER.info("Using protocol version %s", protocol_version)

            ports = {
                "controlPort": self._info.get("controlPort", 7002),
                "notifyPort": self._info.get("notifyPort", 7003),
                "menuNotifyPort": self._info.get("menuNotifyPort", self._info.get("notifyPort", 7003)),
            }
            _LOGGER.info("Using ports: %s", ports)
            
            try:
                self._socket_mgr = SocketManager(self.host, ports)
                await self._socket_mgr.start()
                _LOGGER.debug("Socket manager started")
            except Exception as e:
                _LOGGER.error("Failed to start socket manager: %s", e)
                # Reset state on failure
                self._socket_mgr = None
                raise

            try:
                # Initialize Protocol with the determined protocol version
                self._protocol = Protocol(self._socket_mgr, protocol_version=protocol_version)
                self._dispatcher = Dispatcher(self._socket_mgr, "notifyPort")
                await self._dispatcher.start()
                
                # Phase 1 Fix: Set connected state only after successful initialization
                self._connected = True
                _LOGGER.info("Successfully connected to device at %s using protocol %s", 
                           self.host, protocol_version)
            except Exception as e:
                _LOGGER.error("Failed to initialize protocol or dispatcher: %s", e)
                # Cleanup on failure
                if self._socket_mgr:
                    await self._socket_mgr.stop()
                self._socket_mgr = None
                self._protocol = None
                self._dispatcher = None
                raise

    async def disconnect(self):
        """Unsubscribe & close sockets."""
        # Phase 1 Fix: Protect against concurrent disconnect() calls
        async with self._connection_lock:
            if not self._connected or not self._protocol:
                _LOGGER.debug("Already disconnected")
                return
                
            _LOGGER.info("Disconnecting from device at %s", self.host)
            
            try:
                _LOGGER.debug("Unsubscribing from all properties")
                # Use the proper unsubscribe function with an empty property list
                await self._socket_mgr.send(build_unsubscribe([]), "controlPort")
                
                _LOGGER.debug("Stopping dispatcher")
                await self._dispatcher.stop()
                
                _LOGGER.debug("Stopping socket manager")
                await self._socket_mgr.stop()
                
                _LOGGER.info("Successfully disconnected from device at %s", self.host)
            except Exception as e:
                _LOGGER.error("Error during disconnect: %s", e)
                # Still attempt to clean up
                with contextlib.suppress(Exception):
                    await self._dispatcher.stop()
                with contextlib.suppress(Exception):
                    await self._socket_mgr.stop()
            finally:
                # Phase 1 Fix: Always reset state after disconnect attempt
                self._connected = False
                self._socket_mgr = None
                self._protocol = None
                self._dispatcher = None

    # ---------- subscription helpers ---------------------------------------
    async def subscribe(self, props: Property | Sequence[Property]):
        """Subscribe to property changes from the device."""
        if isinstance(props, Property):
            props = [props]
        names = [p.value for p in props]
        
        _LOGGER.info("Subscribing to properties: %s", names)
        try:
            # Pass the protocol version to build_subscribe
            await self._socket_mgr.send(build_subscribe(names, self._protocol.protocol_version), "controlPort")
            _LOGGER.debug("Subscription request sent")
        except Exception as e:
            _LOGGER.error("Failed to subscribe to properties: %s", e)
            raise

    async def unsubscribe(self, props: Property | Sequence[Property]):
        """Unsubscribe from property changes."""
        if isinstance(props, Property):
            props = [props]
        names = [p.value for p in props]
        
        _LOGGER.info("Unsubscribing from properties: %s", names)
        try:
            # Use the proper unsubscribe function
            await self._socket_mgr.send(build_unsubscribe(names), "controlPort")
            _LOGGER.debug("Unsubscription request sent")
        except Exception as e:
            _LOGGER.error("Failed to unsubscribe from properties: %s", e)
            raise

    def on(self, prop: Property):
        """Register a callback for property changes."""
        def decorator(cb: Callable[[Any], Awaitable[None]] | Callable[[Any], None]):
            _LOGGER.debug("Registering callback for property: %s", prop.value)
            self._dispatcher.on(prop.value, cb)
            return cb
        return decorator

    # ---------- convenience methods ----------------------------------------
    async def power_on(self, *, zone: Zone = Zone.MAIN):
        """Power on the specified zone."""
        _LOGGER.info("Powering on %s zone", zone.name)
        cmd = Command.ZONE2_POWER_ON if zone is Zone.ZONE2 else Command.POWER_ON
        await self._protocol.send_command(cmd.value)

    async def power_off(self, *, zone: Zone = Zone.MAIN):
        """Power off the specified zone."""
        _LOGGER.info("Powering off %s zone", zone.name)
        cmd = Command.ZONE2_POWER_OFF if zone is Zone.ZONE2 else Command.POWER_OFF
        await self._protocol.send_command(cmd.value)

    async def power_toggle(self, *, zone: Zone = Zone.MAIN):
        """Toggle power for the specified zone."""
        _LOGGER.info("Toggling power for %s zone", zone.name)
        cmd = Command.ZONE2_POWER if zone is Zone.ZONE2 else Command.STANDBY
        await self._protocol.send_command(cmd.value)

    async def set_volume(self, db: float, *, zone: Zone = Zone.MAIN):
        """Set volume to a specific level in dB."""
        _LOGGER.info("Setting %s zone volume to %.1f dB", zone.name, db)
        if zone is Zone.ZONE2:
            await self._protocol.send_command(Command.ZONE2_SET_VOLUME.value, {"value": db})
        else:
            await self._protocol.send_command(Command.SET_VOLUME.value, {"value": db})

    async def vol_up(self, step: float = 1.0, *, zone: Zone = Zone.MAIN):
        """Increase volume by the specified step."""
        _LOGGER.info("Volume up by %.1f dB for %s zone", step, zone.name)
        await self.set_volume_relative(step, zone=zone)

    async def vol_down(self, step: float = 1.0, *, zone: Zone = Zone.MAIN):
        """Decrease volume by the specified step."""
        _LOGGER.info("Volume down by %.1f dB for %s zone", step, zone.name)
        await self.set_volume_relative(-step, zone=zone)

    async def set_volume_relative(self, delta: float, *, zone: Zone = Zone.MAIN):
        """Change volume by a relative amount."""
        _LOGGER.info("Changing %s zone volume by %.1f dB", zone.name, delta)
        cmd = Command.ZONE2_VOLUME if zone is Zone.ZONE2 else Command.VOLUME
        await self._protocol.send_command(cmd.value, {"value": delta})

    async def mute(self, *, zone: Zone = Zone.MAIN):
        """Toggle mute for the specified zone."""
        _LOGGER.info("Toggling mute for %s zone", zone.name)
        cmd = Command.ZONE2_MUTE if zone is Zone.ZONE2 else Command.MUTE
        await self._protocol.send_command(cmd.value)

    async def select_input(self, input: Input | str):
        """Select an input source."""
        if isinstance(input, Input):
            input_value = input.value
            input_name = input.name
        else:
            input_value = input.lower()
            input_name = input_value.upper()
            if input_value not in (i.value for i in Input):
                _LOGGER.error("Invalid input: %s", input)
                raise InvalidArgumentError(f"Unknown input {input}")
                
        _LOGGER.info("Selecting input: %s", input_name)
        try:
            await self._protocol.send_command(Command[f"{input_value.upper()}"].value)
        except KeyError:
            _LOGGER.error("Command not found for input: %s", input_value)
            raise InvalidArgumentError(f"Command not found for input {input_value}")

    # ---------- status snapshot --------------------------------------------
    async def status(self, *props: Property, timeout: float = 2.0) -> Dict[Property, str]:
        """Get current status of specified properties."""
        if not props:
            _LOGGER.error("No properties requested in status call")
            raise InvalidArgumentError("Must request at least one property")
            
        names = [p.value for p in props]
        _LOGGER.info("Requesting status for properties: %s (timeout=%.1f)", names, timeout)
        
        try:
            result = await self._protocol.request_properties(names, timeout=timeout)
            return {Property(name): val for name, val in result.items()}
        except Exception as e:
            _LOGGER.error("Error fetching status: %s", e)
            raise
