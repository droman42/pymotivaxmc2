"""High‑level facade for Emotiva devices (v0.2.0)."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Callable, Awaitable, Dict, Any, Sequence, List
from .core.discovery import Discovery
from .core.socket_mgr import SocketManager
from .core.protocol import Protocol
from .core.dispatcher import Dispatcher
from .core.xmlcodec import build_unsubscribe
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
        ack_timeout: Seconds to wait for an ``<emotivaAck>`` before retrying a
            command (passed through to the underlying Protocol).
        max_retries: Default total attempts per control transaction (legacy
            meaning: ``3`` = one send + two re-sends). Per-call ``retries=``
            overrides count RE-sends (``retries=0`` = exactly one send).
        min_send_interval: Minimum seconds between control-port sends
            (0 = unpaced). Emotiva processors have limited processing power;
            pace all control traffic with one knob when driving fragile
            firmware.
    """
    def __init__(self, host: str, *, timeout: float = 5.0, protocol_max: str = "3.1",
                 ack_timeout: float = 2.0, max_retries: int = 3,
                 min_send_interval: float = 0.0):
        self.host = host
        self.timeout = timeout
        self.protocol_max = protocol_max
        self.ack_timeout = ack_timeout
        self.max_retries = max_retries
        self.min_send_interval = min_send_interval
        self._info: Dict[str, Any] | None = None
        self._socket_mgr: SocketManager | None = None
        self._protocol: Protocol | None = None
        self._dispatcher: Dispatcher | None = None
        
        # Phase 1 Fix: Add connection state protection
        self._connection_lock = asyncio.Lock()
        self._connected = False

        # Names subscribed in this session — the spec has no "unsubscribe all"
        # (each property must be unsubscribed explicitly, §2.1.5), so
        # disconnect() needs the real list to actually clear device-side state.
        self._subscribed: set[str] = set()
        
        _LOGGER.info("Initialized controller for device at %s (timeout=%.1f)", host, timeout)

    # ---------- connected-state accessors ----------------------------------
    # The socket manager, protocol and dispatcher only exist between connect()
    # and disconnect(). These accessors narrow the Optional away for the
    # post-connect call sites and turn "used before connect()" from an opaque
    # AttributeError on None into a clear EmotivaError.
    @property
    def _sock(self) -> SocketManager:
        if self._socket_mgr is None:
            raise EmotivaError("Controller is not connected; call connect() first")
        return self._socket_mgr

    @property
    def _proto(self) -> Protocol:
        if self._protocol is None:
            raise EmotivaError("Controller is not connected; call connect() first")
        return self._protocol

    @property
    def _disp(self) -> Dispatcher:
        if self._dispatcher is None:
            raise EmotivaError("Controller is not connected; call connect() first")
        return self._dispatcher

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
                self._protocol = Protocol(self._socket_mgr, protocol_version=protocol_version,
                                          ack_timeout=self.ack_timeout,
                                          max_retries=self.max_retries,
                                          min_send_interval=self.min_send_interval)
                self._dispatcher = Dispatcher(self._socket_mgr, "notifyPort")
                # Let the protocol fan subscribe-time initial values out through
                # the dispatcher's callback path (see Protocol.subscribe).
                self._protocol.dispatcher = self._dispatcher
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
                # The spec has no "unsubscribe all" — each property must be named
                # explicitly (§2.1.5); an empty <emotivaUnsubscribe> clears NOTHING
                # on the device. Send the real subscribed set.
                if self._subscribed:
                    names = sorted(self._subscribed)
                    _LOGGER.debug("Unsubscribing from %d properties: %s", len(names), names)
                    await self._sock.send(build_unsubscribe(names), "controlPort")
                    self._subscribed.clear()
                else:
                    _LOGGER.debug("No active subscriptions to clear")

                _LOGGER.debug("Stopping dispatcher")
                await self._disp.stop()

                _LOGGER.debug("Stopping socket manager")
                await self._sock.stop()

                _LOGGER.info("Successfully disconnected from device at %s", self.host)
            except Exception as e:
                _LOGGER.error("Error during disconnect: %s", e)
                # Still attempt to clean up
                with contextlib.suppress(Exception):
                    await self._disp.stop()
                with contextlib.suppress(Exception):
                    await self._sock.stop()
            finally:
                # Phase 1 Fix: Always reset state after disconnect attempt
                self._connected = False
                self._socket_mgr = None
                self._protocol = None
                self._dispatcher = None

    # ---------- device info accessors ---------------------------------------
    @property
    def keepalive_interval_ms(self) -> int | None:
        """Device-advertised keepAlive interval in milliseconds.

        Parsed from the ``<emotivaTransponder>`` packet at :meth:`connect`
        (spec: the interval at which the device emits its ``keepAlive``
        notification). ``None`` before ``connect()`` or when the device did
        not advertise one — consumers building a liveness watchdog should
        fall back to their own default in that case.
        """
        if self._info is None:
            return None
        ka = self._info.get("keepAlive")
        return int(ka) if ka is not None else None

    @property
    def notification_sequence(self) -> int | None:
        """Sequence number of the last ``emotivaNotify`` received (spec §2.6);
        ``None`` before connect() or before the first notification."""
        if self._dispatcher is None:
            return None
        return self._dispatcher.last_sequence

    @property
    def notification_gaps(self) -> int:
        """Total notifications MISSED so far, detected via sequence-number
        jumps. A non-zero delta since the last check means state built from
        notifications may be stale — refresh what you care about instead of
        blind-polling everything."""
        if self._dispatcher is None:
            return 0
        return self._dispatcher.gap_count

    # ---------- subscription helpers ---------------------------------------
    async def subscribe(self, props: Property | Sequence[Property]) -> Dict[str, Any]:
        """Subscribe to property changes from the device.

        Delegates to :meth:`Protocol.subscribe`, which sends the request, waits
        for the ``<emotivaSubscription>`` confirmation, and returns the device's
        current value for each successfully-subscribed property as
        ``{name: {"value": str, "visible": bool}}`` (the Subscribe response
        carries current values per the Emotiva Remote Interface spec §2.1.3).

        Any callbacks registered via :meth:`on` are additionally invoked with
        each initial value through the same path as ongoing notifications, so
        callback-based consumers reach a consistent state immediately after
        subscribing without piping the return value through by hand.
        """
        if isinstance(props, Property):
            props = [props]
        names = [p.value for p in props]

        _LOGGER.info("Subscribing to properties: %s", names)
        try:
            result = await self._proto.subscribe(names)
            self._subscribed.update(names)
            return result
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
            await self._sock.send(build_unsubscribe(names), "controlPort")
            self._subscribed.difference_update(names)
            _LOGGER.debug("Unsubscription request sent")
        except Exception as e:
            _LOGGER.error("Failed to unsubscribe from properties: %s", e)
            raise

    def on(self, prop: Property):
        """Register a callback for property changes."""
        def decorator(cb: Callable[[Any], Awaitable[None]] | Callable[[Any], None]):
            _LOGGER.debug("Registering callback for property: %s", prop.value)
            self._disp.on(prop.value, cb)
            return cb
        return decorator

    # ---------- convenience methods ----------------------------------------
    async def power_on(self, *, zone: Zone = Zone.MAIN,
                       retries: int | None = None, ack: bool = True):
        """Power on the specified zone."""
        _LOGGER.info("Powering on %s zone", zone.name)
        cmd = Command.ZONE2_POWER_ON if zone is Zone.ZONE2 else Command.POWER_ON
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def power_off(self, *, zone: Zone = Zone.MAIN,
                        retries: int | None = None, ack: bool = True):
        """Power off the specified zone."""
        _LOGGER.info("Powering off %s zone", zone.name)
        cmd = Command.ZONE2_POWER_OFF if zone is Zone.ZONE2 else Command.POWER_OFF
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def power_toggle(self, *, zone: Zone = Zone.MAIN,
                           retries: int | None = None, ack: bool = True):
        """Toggle power for the specified zone."""
        _LOGGER.info("Toggling power for %s zone", zone.name)
        cmd = Command.ZONE2_POWER if zone is Zone.ZONE2 else Command.STANDBY
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def set_volume(self, db: float, *, zone: Zone = Zone.MAIN,
                         retries: int | None = None, ack: bool = True):
        """Set volume to a specific level in dB."""
        _LOGGER.info("Setting %s zone volume to %.1f dB", zone.name, db)
        if zone is Zone.ZONE2:
            await self._proto.send_command(Command.ZONE2_SET_VOLUME.value, {"value": db},
                                           retries=retries, ack=ack)
        else:
            await self._proto.send_command(Command.SET_VOLUME.value, {"value": db},
                                           retries=retries, ack=ack)

    async def vol_up(self, step: float = 1.0, *, zone: Zone = Zone.MAIN,
                     retries: int | None = None, ack: bool = True):
        """Increase volume by the specified step."""
        _LOGGER.info("Volume up by %.1f dB for %s zone", step, zone.name)
        await self.set_volume_relative(step, zone=zone, retries=retries, ack=ack)

    async def vol_down(self, step: float = 1.0, *, zone: Zone = Zone.MAIN,
                       retries: int | None = None, ack: bool = True):
        """Decrease volume by the specified step."""
        _LOGGER.info("Volume down by %.1f dB for %s zone", step, zone.name)
        await self.set_volume_relative(-step, zone=zone, retries=retries, ack=ack)

    async def set_volume_relative(self, delta: float, *, zone: Zone = Zone.MAIN,
                                  retries: int | None = None, ack: bool = True):
        """Change volume by a relative amount."""
        _LOGGER.info("Changing %s zone volume by %.1f dB", zone.name, delta)
        cmd = Command.ZONE2_VOLUME if zone is Zone.ZONE2 else Command.VOLUME
        await self._proto.send_command(cmd.value, {"value": delta}, retries=retries, ack=ack)

    async def mute(self, *, zone: Zone = Zone.MAIN,
                   retries: int | None = None, ack: bool = True):
        """Toggle mute for the specified zone (alias of :meth:`mute_toggle`)."""
        await self.mute_toggle(zone=zone, retries=retries, ack=ack)

    async def mute_toggle(self, *, zone: Zone = Zone.MAIN,
                          retries: int | None = None, ack: bool = True):
        """Toggle mute for the specified zone."""
        _LOGGER.info("Toggling mute for %s zone", zone.name)
        cmd = Command.ZONE2_MUTE if zone is Zone.ZONE2 else Command.MUTE
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def mute_on(self, *, zone: Zone = Zone.MAIN,
                      retries: int | None = None, ack: bool = True):
        """Explicitly mute the specified zone."""
        _LOGGER.info("Muting %s zone", zone.name)
        cmd = Command.ZONE2_MUTE_ON if zone is Zone.ZONE2 else Command.MUTE_ON
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def mute_off(self, *, zone: Zone = Zone.MAIN,
                       retries: int | None = None, ack: bool = True):
        """Explicitly un-mute the specified zone."""
        _LOGGER.info("Un-muting %s zone", zone.name)
        cmd = Command.ZONE2_MUTE_OFF if zone is Zone.ZONE2 else Command.MUTE_OFF
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def select_input(self, input: Input | str, *,
                           retries: int | None = None, ack: bool = True):
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
            await self._proto.send_command(Command[f"{input_value.upper()}"].value,
                                           retries=retries, ack=ack)
        except KeyError:
            _LOGGER.error("Command not found for input: %s", input_value)
            raise InvalidArgumentError(f"Command not found for input {input_value}")

    async def select_source(self, source: int | str, *,
                            retries: int | None = None, ack: bool = True):
        """Select a logical source ("Input N" button), loading its A/V profile.

        Unlike :meth:`select_input` (which selects a raw physical connector such
        as ``hdmi1``), this issues the ``source_N`` / ``source_tuner`` commands
        that mirror the physical remote's "Input N" buttons. These load the full
        configured source profile and carry the user-assigned input name.

        Protocol reference (docs/Emotiva_Remote_Interface_Description.md):
        - ``source_1`` .. ``source_8`` = "Set source to Input N" (lines 450-457)
        - ``source_tuner`` = "Set source to Tuner" (line 449)
        Each is a standard command transaction (section 3.2, lines 238-261):
        ``<emotivaControl><source_N value="0" ack="yes"/></emotivaControl>``,
        acknowledged with ``<emotivaAck><source_N status="ack"/></emotivaAck>``.

        Args:
            source: Integer 1-8 for ``source_1`` .. ``source_8``, or the string
                ``"tuner"`` for ``source_tuner``.

        Raises:
            InvalidArgumentError: If the source is not 1-8 or ``"tuner"``.
        """
        if isinstance(source, str) and source.strip().lower() == "tuner":
            cmd = Command.SOURCE_TUNER
            label = "tuner"
        elif isinstance(source, bool):
            # bool is a subclass of int; reject explicitly to avoid True -> source_1
            raise InvalidArgumentError(f"Invalid source: {source!r}")
        elif isinstance(source, int) and 1 <= source <= 8:
            cmd = Command[f"SOURCE_{source}"]
            label = f"Input {source}"
        else:
            _LOGGER.error("Invalid source: %r", source)
            raise InvalidArgumentError(
                f"Invalid source {source!r}; expected an integer 1-8 or 'tuner'"
            )

        _LOGGER.info("Selecting source: %s (%s)", label, cmd.value)
        await self._proto.send_command(cmd.value, retries=retries, ack=ack)

    async def get_input_names(self, *, timeout: float = 2.0,
                              retries: int | None = None) -> Dict[int, Dict[str, Any]]:
        """Read the user-assigned Input Button names and their visibility.

        Reads properties ``input_1`` .. ``input_8`` — "User name assigned to
        Input Button N" (docs/Emotiva_Remote_Interface_Description.md lines
        642-649). The device reports each with a ``visible`` attribute in the
        Update response (lines 305-312, 427-439, e.g.
        ``<property name="input_1" value="HDMI 1" visible="true" status="ack"/>``);
        hidden buttons report ``visible="false"`` and can be filtered by callers.

        Returns:
            Mapping of button number to its attributes, e.g.
            ``{1: {"name": "ZAPPITI", "visible": True}, ...}``. Buttons the
            device does not report are omitted.
        """
        names = [Property[f"INPUT_{i}"].value for i in range(1, 9)]
        _LOGGER.info("Requesting input button names: %s (timeout=%.1f)", names, timeout)
        result = await self._proto.request_properties_full(names, timeout=timeout, retries=retries)
        out: Dict[int, Dict[str, Any]] = {}
        for i in range(1, 9):
            key = f"input_{i}"
            if key in result:
                out[i] = {"name": result[key]["value"], "visible": result[key]["visible"]}
        return out

    # ---------- status snapshot --------------------------------------------
    async def status(self, *props: Property, timeout: float = 2.0,
                     retries: int | None = None) -> Dict[Property, str]:
        """Get current status of specified properties."""
        if not props:
            _LOGGER.error("No properties requested in status call")
            raise InvalidArgumentError("Must request at least one property")
            
        names = [p.value for p in props]
        _LOGGER.info("Requesting status for properties: %s (timeout=%.1f)", names, timeout)
        
        try:
            result = await self._proto.request_properties(names, timeout=timeout, retries=retries)
            return {Property(name): val for name, val in result.items()}
        except Exception as e:
            _LOGGER.error("Error fetching status: %s", e)
            raise
