"""Handles command / ack round‑trip semantics."""
from __future__ import annotations

import asyncio
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
        _LOGGER.debug("Protocol initialized with version=%s, ack_timeout=%.1f", 
                    protocol_version, ack_timeout)

    async def send_command(self, name: str, params: dict[str, Any] | None = None):
        _LOGGER.info("Sending command '%s' with params %s", name, params)
        data = build_command(name, self.protocol_version, **(params or {}))
        await self.socket_mgr.send(data, "controlPort")
        
        # Wait for ack on same port
        _LOGGER.debug("Waiting for ack on controlPort (timeout=%.1f)", self.ack_timeout)
        try:
            xml_bytes, _ = await self.socket_mgr.recv("controlPort", timeout=self.ack_timeout)
            xml = parse_xml(xml_bytes)
            
            if xml.tag != "emotivaAck":
                _LOGGER.warning("Unexpected response tag: %s (expected 'emotivaAck')", xml.tag)
                raise AckTimeoutError(f"Unexpected response: {xml.tag}")
                
            _LOGGER.info("Received ack for command '%s'", name)
            return xml
        except asyncio.TimeoutError:
            _LOGGER.error("Ack timeout for command '%s' after %.1f seconds", name, self.ack_timeout)
            raise AckTimeoutError(f"No ack received for command '{name}'")

    async def request_properties(self, properties: list[str], timeout: float = 2.0) -> dict[str, str]:
        _LOGGER.info("Requesting properties: %s (timeout=%.1f)", properties, timeout)
        await self.socket_mgr.send(build_update(properties, self.protocol_version), "controlPort")
        
        results = {}
        try:
            _LOGGER.debug("Waiting for property responses...")
            start_time = asyncio.get_event_loop().time()
            remaining_time = timeout
            
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
                    remaining_time = timeout - elapsed
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout waiting for more property responses")
                    break
                    
            # Log completion status
            if len(results) == len(properties):
                _LOGGER.info("Received all requested properties")
            else:
                missing = set(properties) - set(results.keys())
                _LOGGER.warning("Missing properties in response: %s", missing)
                
            return results
        except Exception as e:
            _LOGGER.error("Error requesting properties: %s", e)
            raise

    async def subscribe(self, properties: list[str]) -> Dict[str, Any]:
        """Subscribe to property updates."""
        _LOGGER.info("Subscribing to properties: %s", properties)
        await self.socket_mgr.send(build_subscribe(properties, self.protocol_version), "controlPort")
        
        # Wait for subscription confirmation
        try:
            xml_bytes, _ = await self.socket_mgr.recv("controlPort", timeout=self.ack_timeout)
            xml = parse_xml(xml_bytes)
            
            if xml.tag != "emotivaSubscription":
                _LOGGER.warning("Unexpected response tag: %s (expected 'emotivaSubscription')", xml.tag)
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
                        
            _LOGGER.info("Successfully subscribed to %d/%d properties", len(results), len(properties))
            return results
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting for subscription confirmation")
            raise AckTimeoutError("No subscription confirmation received")
