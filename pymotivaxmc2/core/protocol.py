"""Handles command / ack round‑trip semantics."""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, Optional

from .logging import get_logger
from .xmlcodec import build_command, build_update, build_subscribe, parse_xml
from ..exceptions import AckTimeoutError

# Module logger
_LOGGER = get_logger("protocol")

class Protocol:
    def __init__(self, socket_mgr, protocol_version: str = "2.0", ack_timeout: float = 2.0):
        self.socket_mgr = socket_mgr
        self.protocol_version = protocol_version
        self.ack_timeout = ack_timeout
        
        # Phase 2 Fix: Add command concurrency control and retry configuration
        self._command_semaphore = asyncio.Semaphore(5)  # Limit concurrent commands
        self._max_retries = 3
        self._base_backoff = 0.5  # Base backoff time in seconds
        self._max_backoff = 8.0   # Maximum backoff time
        
        _LOGGER.debug("Protocol initialized with version=%s, ack_timeout=%.1f, max_concurrent=5", 
                    protocol_version, ack_timeout)

    async def send_command(self, name: str, params: dict[str, Any] | None = None):
        """Send command with exponential backoff retry and concurrency control."""
        # Phase 2 Fix: Limit concurrent commands to prevent resource exhaustion
        async with self._command_semaphore:
            _LOGGER.info("Sending command '%s' with params %s", name, params)
            data = build_command(name, self.protocol_version, **(params or {}))
            
            # Phase 2 Fix: Implement exponential backoff retry
            last_exception = None
            for attempt in range(self._max_retries):
                try:
                    # Calculate timeout with backoff
                    timeout = self.ack_timeout
                    if attempt > 0:
                        backoff = min(self._base_backoff * (2 ** (attempt - 1)), self._max_backoff)
                        jitter = random.uniform(0, 0.1 * backoff)  # Add jitter
                        timeout = self.ack_timeout + backoff + jitter
                        _LOGGER.debug("Retry %d/%d with timeout %.2f (backoff: %.2f)", 
                                    attempt + 1, self._max_retries, timeout, backoff)
                    
                    await self.socket_mgr.send(data, "controlPort")
                    
                    # Wait for ack on same port
                    _LOGGER.debug("Waiting for ack on controlPort (timeout=%.2f)", timeout)
                    xml_bytes, _ = await self.socket_mgr.recv("controlPort", timeout=timeout)
                    xml = parse_xml(xml_bytes)
                    
                    if xml.tag != "emotivaAck":
                        _LOGGER.warning("Unexpected response tag: %s (expected 'emotivaAck')", xml.tag)
                        raise AckTimeoutError(f"Unexpected response: {xml.tag}")
                        
                    _LOGGER.info("Received ack for command '%s' (attempt %d)", name, attempt + 1)
                    return xml
                    
                except asyncio.TimeoutError as e:
                    last_exception = AckTimeoutError(f"No ack received for command '{name}' (attempt {attempt + 1})")
                    if attempt < self._max_retries - 1:
                        backoff_time = min(self._base_backoff * (2 ** attempt), self._max_backoff)
                        jitter = random.uniform(0, 0.1 * backoff_time)
                        sleep_time = backoff_time + jitter
                        _LOGGER.warning("Command '%s' timeout on attempt %d, retrying in %.2f seconds", 
                                      name, attempt + 1, sleep_time)
                        await asyncio.sleep(sleep_time)
                    else:
                        _LOGGER.error("Command '%s' failed after %d attempts", name, self._max_retries)
                except Exception as e:
                    # Phase 2 Fix: Improved error categorization
                    if attempt < self._max_retries - 1:
                        _LOGGER.warning("Command '%s' error on attempt %d: %s, retrying", 
                                      name, attempt + 1, e)
                        await asyncio.sleep(self._base_backoff * (attempt + 1))
                    else:
                        _LOGGER.error("Command '%s' failed after %d attempts: %s", 
                                    name, self._max_retries, e)
                        raise
            
            # All retries exhausted
            raise last_exception

    async def request_properties(self, properties: list[str], timeout: float = 2.0) -> dict[str, str]:
        """Request properties with improved error handling and timeout management."""
        # Phase 2 Fix: Apply concurrency limits to property requests
        async with self._command_semaphore:
            _LOGGER.info("Requesting properties: %s (timeout=%.1f)", properties, timeout)
            
            # Phase 2 Fix: Retry property requests with backoff
            last_exception = None
            for attempt in range(self._max_retries):
                try:
                    # Calculate adaptive timeout
                    adaptive_timeout = timeout
                    if attempt > 0:
                        adaptive_timeout = timeout * (1.5 ** attempt)
                        _LOGGER.debug("Property request retry %d with timeout %.2f", 
                                    attempt + 1, adaptive_timeout)
                    
                    await self.socket_mgr.send(build_update(properties, self.protocol_version), "controlPort")
                    
                    results = {}
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
                                            results[prop_name] = prop_elem.get("value", "")
                                            _LOGGER.debug("Received property '%s' = '%s' (v3.0+ format)", 
                                                        prop_name, results[prop_name])
                                # Protocol 2.0 uses direct element names
                                else:
                                    for prop_elem in xml:
                                        if prop_elem.tag in properties:
                                            results[prop_elem.tag] = prop_elem.text or prop_elem.get("value", "")
                                            _LOGGER.debug("Received property '%s' = '%s' (v2.0 format)",
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
                        if attempt < self._max_retries - 1:
                            _LOGGER.warning("Missing properties %s on attempt %d, retrying", missing, attempt + 1)
                            await asyncio.sleep(self._base_backoff * (attempt + 1))
                            continue
                        else:
                            _LOGGER.warning("Missing properties in final response: %s", missing)
                            return results
                            
                except Exception as e:
                    last_exception = e
                    if attempt < self._max_retries - 1:
                        _LOGGER.warning("Property request error on attempt %d: %s, retrying", 
                                      attempt + 1, e)
                        await asyncio.sleep(self._base_backoff * (attempt + 1))
                    else:
                        _LOGGER.error("Property request failed after %d attempts: %s", 
                                    self._max_retries, e)
                        raise
            
            if last_exception:
                raise last_exception

    async def subscribe(self, properties: list[str]) -> Dict[str, Any]:
        """Subscribe to property updates with retry logic."""
        # Phase 2 Fix: Apply concurrency limits and retry to subscriptions
        async with self._command_semaphore:
            _LOGGER.info("Subscribing to properties: %s", properties)
            
            last_exception = None
            for attempt in range(self._max_retries):
                try:
                    # Calculate adaptive timeout
                    timeout = self.ack_timeout
                    if attempt > 0:
                        timeout = self.ack_timeout * (1.5 ** attempt)
                        _LOGGER.debug("Subscription retry %d with timeout %.2f", attempt + 1, timeout)
                    
                    await self.socket_mgr.send(build_subscribe(properties, self.protocol_version), "controlPort")
                    
                    # Wait for subscription confirmation
                    xml_bytes, _ = await self.socket_mgr.recv("controlPort", timeout=timeout)
                    xml = parse_xml(xml_bytes)
                    
                    if xml.tag != "emotivaSubscription":
                        _LOGGER.warning("Unexpected response tag: %s (expected 'emotivaSubscription')", xml.tag)
                        if attempt < self._max_retries - 1:
                            await asyncio.sleep(self._base_backoff * (attempt + 1))
                            continue
                        return {}
                        
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
                    return results
                    
                except asyncio.TimeoutError as e:
                    last_exception = AckTimeoutError("No subscription confirmation received")
                    if attempt < self._max_retries - 1:
                        backoff_time = self._base_backoff * (2 ** attempt)
                        _LOGGER.warning("Subscription timeout on attempt %d, retrying in %.2f seconds", 
                                      attempt + 1, backoff_time)
                        await asyncio.sleep(backoff_time)
                    else:
                        _LOGGER.error("Subscription failed after %d attempts", self._max_retries)
                except Exception as e:
                    last_exception = e
                    if attempt < self._max_retries - 1:
                        _LOGGER.warning("Subscription error on attempt %d: %s, retrying", 
                                      attempt + 1, e)
                        await asyncio.sleep(self._base_backoff * (attempt + 1))
                    else:
                        _LOGGER.error("Subscription failed after %d attempts: %s", 
                                    self._max_retries, e)
                        raise
            
            if last_exception:
                raise last_exception
