"""Handles command / ack round‑trip semantics."""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict

from .logging import get_logger
from .xmlcodec import build_command, build_update, build_subscribe, parse_xml
from .dispatcher import Dispatcher
from ..exceptions import AckTimeoutError

# Module logger
_LOGGER = get_logger("protocol")

class Protocol:
    def __init__(self, socket_mgr, protocol_version: str = "2.0", ack_timeout: float = 2.0,
                 max_retries: int = 3, min_send_interval: float = 0.0):
        """Args:
            socket_mgr: The bound :class:`SocketManager`.
            protocol_version: Negotiated protocol version string.
            ack_timeout: Seconds to wait for a transaction's reply per attempt.
            max_retries: Default total attempts per transaction (legacy meaning,
                kept for compatibility: ``3`` = one send + two re-sends). Per-call
                ``retries=`` overrides count RE-sends: ``retries=0`` is exactly
                one attempt.
            min_send_interval: Minimum seconds between control-port sends
                (0 = unpaced). Emotiva processors have limited processing power;
                consumers driving fragile firmware can pace all control traffic
                with one knob.
        """
        self.socket_mgr = socket_mgr
        self.protocol_version = protocol_version
        self.ack_timeout = ack_timeout

        # Optional dispatcher used to fan subscribe-time initial values out to
        # registered listeners. Wired up by the controller after both are
        # constructed; stays ``None`` when the protocol is used standalone.
        self.dispatcher: Dispatcher | None = None

        # Control-port transactions are SERIALIZED: exactly one request/response
        # transaction (command / subscribe / update) is in flight at any time.
        # Emotiva processors have limited processing power — concurrent control
        # traffic can grind the device to a halt (the openHAB Emotiva binding
        # documents the same failure) — and all control replies arrive on one
        # unkeyed UDP queue, so concurrent transactions used to steal each
        # other's replies (false timeouts -> silent retry storms). One
        # transaction at a time removes both failure modes by construction.
        self._control_lock = asyncio.Lock()
        self._max_retries = max_retries
        self._base_backoff = 0.5  # Base backoff time in seconds
        self._max_backoff = 8.0   # Maximum backoff time
        self._min_send_interval = min_send_interval
        self._last_send_monotonic: float | None = None

        _LOGGER.debug("Protocol initialized with version=%s, ack_timeout=%.1f (serialized control port, "
                    "max_retries=%d, min_send_interval=%.2f)",
                    protocol_version, ack_timeout, max_retries, min_send_interval)

    def _attempts(self, retries: int | None) -> int:
        """Total attempts for a transaction.

        ``retries`` counts RE-sends after the first attempt (``0`` = exactly one
        send, for readiness-sensitive callers that must not multiply packets at
        a busy device). ``None`` falls back to the constructor's ``max_retries``,
        which keeps its legacy total-attempts meaning.
        """
        if retries is None:
            return max(1, self._max_retries)
        if retries < 0:
            raise ValueError(f"retries must be >= 0, got {retries}")
        return retries + 1

    async def _send_control(self, data: bytes) -> None:
        """Pace, drain stale frames, and send one control-port datagram."""
        if self._min_send_interval > 0 and self._last_send_monotonic is not None:
            loop = asyncio.get_event_loop()
            wait = self._min_send_interval - (loop.time() - self._last_send_monotonic)
            if wait > 0:
                _LOGGER.debug("Pacing control-port send: sleeping %.3fs", wait)
                await asyncio.sleep(wait)
        self.socket_mgr.drain("controlPort")
        await self.socket_mgr.send(data, "controlPort")
        self._last_send_monotonic = asyncio.get_event_loop().time()

    async def _recv_expected(self, expected_tag: str, timeout: float):
        """Receive control-port frames until one matches ``expected_tag``.

        Frames with any other tag are STALE (late replies from an earlier
        timed-out transaction — the device answers when it can, not when we
        stopped waiting) — they are logged and discarded, and the wait
        continues within the same deadline. This must never raise on an
        unexpected tag: raising here used to convert one stale frame into a
        full transaction retry (more packets at the device).

        Raises:
            asyncio.TimeoutError: if no matching frame arrives in ``timeout``.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            xml_bytes, _ = await self.socket_mgr.recv("controlPort", timeout=remaining)
            xml = parse_xml(xml_bytes)
            if xml.tag == expected_tag:
                return xml
            _LOGGER.warning("Discarding stale control-port frame '%s' (waiting for '%s')",
                            xml.tag, expected_tag)

    async def send_command(self, name: str, params: dict[str, Any] | None = None,
                           *, retries: int | None = None, ack: bool = True):
        """Send a command as one serialized control-port transaction.

        The control lock guarantees no other transaction is in flight; stale
        frames from earlier timed-out transactions are drained before the send,
        and any that arrive mid-wait are discarded by :meth:`_recv_expected`
        rather than failing the attempt (a stale frame used to convert into a
        full transaction retry — more packets at the device).

        Args:
            name: Protocol command name (e.g. ``power_on``).
            params: Extra attributes for the command element.
            retries: RE-sends after the first attempt; ``0`` = exactly one send
                (readiness-sensitive callers must not multiply packets at a busy
                device). ``None`` = the constructor default.
            ack: When ``False``, the command is built with ``ack="no"`` and sent
                fire-and-forget — no reply is awaited, no retries occur, and the
                return value is ``None``. Per spec the ack is optional.

        Returns:
            The parsed ``<emotivaAck>`` element, or ``None`` when ``ack=False``.
        """
        async with self._control_lock:
            _LOGGER.info("Sending command '%s' with params %s (retries=%s, ack=%s)",
                         name, params, retries, ack)
            attributes: dict[str, Any] = dict(params or {})
            attributes["ack"] = "yes" if ack else "no"
            data = build_command(name, self.protocol_version, **attributes)

            if not ack:
                # Fire-and-forget: nothing will come back, so there is nothing
                # to wait for and no signal to retry on.
                await self._send_control(data)
                _LOGGER.debug("Command '%s' sent fire-and-forget (ack='no')", name)
                return None

            attempts = self._attempts(retries)
            last_exception: Exception | None = None
            for attempt in range(attempts):
                try:
                    # Calculate timeout with backoff
                    timeout = self.ack_timeout
                    if attempt > 0:
                        backoff = min(self._base_backoff * (2 ** (attempt - 1)), self._max_backoff)
                        jitter = random.uniform(0, 0.1 * backoff)  # Add jitter
                        timeout = self.ack_timeout + backoff + jitter
                        _LOGGER.debug("Retry %d/%d with timeout %.2f (backoff: %.2f)",
                                    attempt + 1, attempts, timeout, backoff)

                    await self._send_control(data)

                    # Wait for the ack; stale frames are discarded inside.
                    _LOGGER.debug("Waiting for ack on controlPort (timeout=%.2f)", timeout)
                    xml = await self._recv_expected("emotivaAck", timeout)
                    _LOGGER.info("Received ack for command '%s' (attempt %d)", name, attempt + 1)
                    return xml
                    
                except asyncio.TimeoutError:
                    last_exception = AckTimeoutError(f"No ack received for command '{name}' (attempt {attempt + 1})")
                    if attempt < attempts - 1:
                        backoff_time = min(self._base_backoff * (2 ** attempt), self._max_backoff)
                        jitter = random.uniform(0, 0.1 * backoff_time)
                        sleep_time = backoff_time + jitter
                        _LOGGER.warning("Command '%s' timeout on attempt %d, retrying in %.2f seconds", 
                                      name, attempt + 1, sleep_time)
                        await asyncio.sleep(sleep_time)
                    else:
                        _LOGGER.error("Command '%s' failed after %d attempts", name, attempts)
                except Exception as e:
                    if attempt < attempts - 1:
                        _LOGGER.warning("Command '%s' error on attempt %d: %s, retrying", 
                                      name, attempt + 1, e)
                        await asyncio.sleep(self._base_backoff * (attempt + 1))
                    else:
                        _LOGGER.error("Command '%s' failed after %d attempts: %s",
                                    name, attempts, e)
                        raise

            # All retries exhausted
            if last_exception is not None:
                raise last_exception
            raise AckTimeoutError(
                f"Command '{name}' failed after {attempts} attempts"
            )

    async def request_properties(self, properties: list[str], timeout: float = 2.0,
                                 *, retries: int | None = None) -> dict[str, str]:
        """Request properties and return a name -> value mapping.

        This is a thin wrapper over :meth:`request_properties_full` that discards
        the per-property ``visible`` attribute, preserving the historical return
        shape. Use :meth:`request_properties_full` when the visibility flag is
        needed (e.g. reading Input Button names; see doc Update response
        Emotiva_Remote_Interface_Description.md lines 427-439).
        """
        full = await self.request_properties_full(properties, timeout=timeout, retries=retries)
        return {name: attrs["value"] for name, attrs in full.items()}

    async def request_properties_full(
        self, properties: list[str], timeout: float = 2.0, *, retries: int | None = None
    ) -> dict[str, dict[str, Any]]:
        """Request properties and return full attributes per property.

        Returns a mapping ``{name: {"value": str, "visible": bool}}``.

        The ``visible`` attribute is reported by the device in the Update
        response (doc Emotiva_Remote_Interface_Description.md lines 427-439, e.g.
        ``<property name="source" value="HDMI 1" visible="true" status="ack"/>``)
        and is defaulted to ``True`` when absent (e.g. Protocol 2.0 responses,
        which the doc only specifies with element names and no visible flag).
        """
        async with self._control_lock:
            _LOGGER.info("Requesting properties: %s (timeout=%.1f, retries=%s)",
                         properties, timeout, retries)

            attempts = self._attempts(retries)
            # Results ACCUMULATE across attempts, and each retry re-requests only
            # the still-missing properties — never the whole batch (re-sending the
            # full batch multiplied packets at the device exactly when it was
            # slow to answer).
            results: dict[str, dict[str, Any]] = {}
            last_exception = None
            for attempt in range(attempts):
                try:
                    outstanding = [p for p in properties if p not in results]
                    if not outstanding:
                        return results
                    # Calculate adaptive timeout
                    adaptive_timeout = timeout
                    if attempt > 0:
                        adaptive_timeout = timeout * (1.5 ** attempt)
                        _LOGGER.debug("Property request retry %d for missing %s with timeout %.2f",
                                    attempt + 1, outstanding, adaptive_timeout)

                    await self._send_control(build_update(outstanding, self.protocol_version))

                    start_time = asyncio.get_event_loop().time()
                    remaining_time = adaptive_timeout

                    while len(results) < len(properties) and remaining_time > 0:
                        try:
                            xml_bytes, _ = await self.socket_mgr.recv("controlPort", timeout=remaining_time)
                            xml = parse_xml(xml_bytes)

                            if xml.tag == "emotivaNotify" or xml.tag == "emotivaUpdate":
                                # Protocol 3.0+ uses property elements with name attributes
                                if self.protocol_version >= "3.0":
                                    for prop_elem in xml.findall("property"):
                                        prop_name = prop_elem.get("name")
                                        if prop_name in properties:
                                            results[prop_name] = {
                                                "value": prop_elem.get("value", ""),
                                                "visible": prop_elem.get("visible", "true") == "true",
                                            }
                                            _LOGGER.debug("Received property '%s' = %s (v3.0+ format)",
                                                        prop_name, results[prop_name])
                                # Protocol 2.0 uses direct element names
                                else:
                                    for prop_elem in xml:
                                        if prop_elem.tag in properties:
                                            results[prop_elem.tag] = {
                                                "value": prop_elem.text or prop_elem.get("value", ""),
                                                "visible": prop_elem.get("visible", "true") == "true",
                                            }
                                            _LOGGER.debug("Received property '%s' = %s (v2.0 format)",
                                                        prop_elem.tag, results[prop_elem.tag])
                            else:
                                _LOGGER.debug("Received unexpected tag '%s'", xml.tag)

                            # Update remaining time
                            elapsed = asyncio.get_event_loop().time() - start_time
                            remaining_time = adaptive_timeout - elapsed
                        except asyncio.TimeoutError:
                            _LOGGER.warning("Timeout waiting for more property responses")
                            break

                    # Log completion status
                    if len(results) == len(properties):
                        _LOGGER.info("Received all requested properties (attempt %d)", attempt + 1)
                        return results
                    else:
                        missing = set(properties) - set(results.keys())
                        if attempt < attempts - 1:
                            _LOGGER.warning("Missing properties %s on attempt %d, retrying (missing only)",
                                          missing, attempt + 1)
                            await asyncio.sleep(self._base_backoff * (attempt + 1))
                            continue
                        else:
                            _LOGGER.warning("Missing properties in final response: %s", missing)
                            return results

                except Exception as e:
                    last_exception = e
                    if attempt < attempts - 1:
                        _LOGGER.warning("Property request error on attempt %d: %s, retrying",
                                      attempt + 1, e)
                        await asyncio.sleep(self._base_backoff * (attempt + 1))
                    else:
                        _LOGGER.error("Property request failed after %d attempts: %s",
                                    attempts, e)
                        raise

            if last_exception:
                raise last_exception
            return results

    async def subscribe(self, properties: list[str], *, retries: int | None = None) -> Dict[str, Any]:
        """Subscribe to property updates (one serialized transaction).

        Args:
            properties: Property names to subscribe to.
            retries: RE-sends after the first attempt; ``0`` = exactly one send.
                ``None`` = the constructor default.
        """
        async with self._control_lock:
            _LOGGER.info("Subscribing to properties: %s (retries=%s)", properties, retries)

            attempts = self._attempts(retries)
            last_exception: Exception | None = None
            for attempt in range(attempts):
                try:
                    # Calculate adaptive timeout
                    timeout = self.ack_timeout
                    if attempt > 0:
                        timeout = self.ack_timeout * (1.5 ** attempt)
                        _LOGGER.debug("Subscription retry %d with timeout %.2f", attempt + 1, timeout)
                    
                    await self._send_control(build_subscribe(properties, self.protocol_version))

                    # Wait for the subscription confirmation; stale frames are
                    # discarded inside instead of burning the attempt.
                    xml = await self._recv_expected("emotivaSubscription", timeout)

                    results = {}
                    # Protocol 3.0+ uses property elements with name attributes
                    if self.protocol_version >= "3.0":
                        for prop_elem in xml.findall("property"):
                            prop_name = prop_elem.get("name")
                            status = prop_elem.get("status")
                            if status == "ack":
                                results[prop_name] = {
                                    "value": prop_elem.get("value", ""),
                                    "visible": prop_elem.get("visible", "true") == "true"
                                }
                                _LOGGER.debug("Subscribed to '%s' = '%s'", prop_name, results[prop_name])
                            else:
                                _LOGGER.warning("Failed to subscribe to '%s'", prop_name)
                    # Protocol 2.0 uses direct element names
                    else:
                        for prop_elem in xml:
                            status = prop_elem.get("status")
                            if status == "ack":
                                results[prop_elem.tag] = {
                                    "value": prop_elem.get("value", ""),
                                    "visible": prop_elem.get("visible", "true") == "true"
                                }
                                _LOGGER.debug("Subscribed to '%s' = '%s'", prop_elem.tag, results[prop_elem.tag])
                            else:
                                _LOGGER.warning("Failed to subscribe to '%s'", prop_elem.tag)
                                
                    _LOGGER.info("Successfully subscribed to %d/%d properties (attempt %d)",
                               len(results), len(properties), attempt + 1)

                    # Fan the initial values the device just sent us out to any
                    # registered listeners, so consumers that use the @on(prop)
                    # callback pattern receive subscribe-time state through the
                    # same path as ongoing notifications. The return value is
                    # unaffected (backward-compatible for callback-less callers).
                    await self._dispatch_initial_values(results)

                    return results
                    
                except asyncio.TimeoutError:
                    last_exception = AckTimeoutError("No subscription confirmation received")
                    if attempt < attempts - 1:
                        backoff_time = self._base_backoff * (2 ** attempt)
                        _LOGGER.warning("Subscription timeout on attempt %d, retrying in %.2f seconds", 
                                      attempt + 1, backoff_time)
                        await asyncio.sleep(backoff_time)
                    else:
                        _LOGGER.error("Subscription failed after %d attempts", attempts)
                except Exception as e:
                    last_exception = e
                    if attempt < attempts - 1:
                        _LOGGER.warning("Subscription error on attempt %d: %s, retrying", 
                                      attempt + 1, e)
                        await asyncio.sleep(self._base_backoff * (attempt + 1))
                    else:
                        _LOGGER.error("Subscription failed after %d attempts: %s",
                                    attempts, e)
                        raise

            if last_exception:
                raise last_exception
            return {}

    async def _dispatch_initial_values(self, results: Dict[str, Dict[str, Any]]) -> None:
        """Push subscribe-time values through the dispatcher's callback path.

        The Subscribe response already carries the current value of every
        successfully-subscribed property (Emotiva Remote Interface spec
        §2.1.3). Rather than make callback-based consumers re-read the return
        value to seed their state, we replay each value through the same
        dispatcher that handles ongoing ``emotivaNotify`` packets — a single
        update path for subscribe-time and notification-time data.

        No-op when no dispatcher is wired (standalone protocol use). Each
        dispatch is guarded so a misbehaving consumer callback cannot break the
        subscription; this mirrors the per-callback resilience already in
        :meth:`Dispatcher._dispatch_property`.
        """
        dispatcher = self.dispatcher
        if dispatcher is None:
            return
        for prop_name, info in results.items():
            if not dispatcher.has_listeners(prop_name):
                continue
            try:
                await dispatcher.dispatch(prop_name, info["value"])
            except Exception as ex:
                _LOGGER.exception(
                    "Initial-value dispatch for '%s' raised: %s", prop_name, ex
                )
