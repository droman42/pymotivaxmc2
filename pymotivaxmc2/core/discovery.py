"""Performs unicast discovery ping to obtain transponder XML."""
from __future__ import annotations

import asyncio
import random
from xml.etree import ElementTree as ET
from typing import Dict, Any

from .logging import get_logger, log_xml

# Module logger
_LOGGER = get_logger("discovery")

class DiscoveryError(Exception):
    ...

# Updated to use protocol attribute instead of version as per the spec
PING_XML = b"""<?xml version="1.0" encoding="utf-8"?><emotivaPing protocol="3.1"/>"""

class Discovery:
    def __init__(self, host: str, *, timeout: float = 5.0):
        self.host = host
        self.timeout = timeout
        
        # Phase 2 Fix: Add retry configuration for discovery resilience
        self._max_retries = 3
        self._base_backoff = 1.0  # Base backoff time in seconds
        
        _LOGGER.debug("Discovery initialized for host %s (timeout=%.1f, max_retries=%d)", 
                    host, timeout, self._max_retries)

    async def fetch_transponder(self) -> Dict[str, Any]:
        """Send ping to port 7000 and wait for transponder on 7001 with retry logic."""
        _LOGGER.info("Discovering device at %s", self.host)
        
        # Phase 2 Fix: Implement retry logic with exponential backoff
        last_exception = None
        for attempt in range(self._max_retries):
            try:
                # Calculate adaptive timeout
                adaptive_timeout = self.timeout
                if attempt > 0:
                    adaptive_timeout = self.timeout * (1.2 ** attempt)  # Modest increase
                    _LOGGER.debug("Discovery retry %d with timeout %.2f", attempt + 1, adaptive_timeout)
                
                loop = asyncio.get_running_loop()
                recv_fut = loop.create_future()
                host = self.host  # Store host locally for _Proto to access

                class _Proto(asyncio.DatagramProtocol):
                    def datagram_received(self, data, addr):
                        if addr[0] == host:  # Use the host from outer scope
                            _LOGGER.debug("Received %d bytes from %s:%d", len(data), addr[0], addr[1])
                            log_xml(_LOGGER, "received", data)
                            recv_fut.set_result(data)
                        else:
                            _LOGGER.warning("Received data from unexpected source %s (expected %s)", addr[0], host)

                transport = None
                try:
                    _LOGGER.debug("Binding to port 7001 for transponder response (attempt %d)", attempt + 1)
                    transport, _ = await loop.create_datagram_endpoint(
                        lambda: _Proto(),
                        local_addr=("0.0.0.0", 7001),
                    )
                    
                    _LOGGER.debug("Sending ping to %s:7000", self.host)
                    log_xml(_LOGGER, "sent", PING_XML)
                    transport.sendto(PING_XML, (self.host, 7000))

                    try:
                        _LOGGER.debug("Waiting for transponder response (timeout=%.2f)", adaptive_timeout)
                        data = await asyncio.wait_for(recv_fut, timeout=adaptive_timeout)
                        _LOGGER.info("Received transponder response from %s (attempt %d)", self.host, attempt + 1)
                        
                        # Parse and return result on success
                        return self._parse_transponder_data(data)
                        
                    except asyncio.TimeoutError as e:
                        last_exception = DiscoveryError(f"No transponder reply (attempt {attempt + 1})")
                        if attempt < self._max_retries - 1:
                            backoff_time = self._base_backoff * (2 ** attempt) + random.uniform(0, 0.5)
                            _LOGGER.warning("Discovery timeout on attempt %d, retrying in %.2f seconds", 
                                          attempt + 1, backoff_time)
                            await asyncio.sleep(backoff_time)
                        else:
                            _LOGGER.error("No transponder reply from %s after %d attempts", 
                                        self.host, self._max_retries)
                finally:
                    if transport:
                        transport.close()
                        
            except OSError as e:
                # Handle port binding issues
                last_exception = DiscoveryError(f"Network error during discovery (attempt {attempt + 1}): {e}")
                if attempt < self._max_retries - 1:
                    backoff_time = self._base_backoff * (attempt + 1) + random.uniform(0, 0.3)
                    _LOGGER.warning("Discovery network error on attempt %d: %s, retrying in %.2f seconds", 
                                  attempt + 1, e, backoff_time)
                    await asyncio.sleep(backoff_time)
                else:
                    _LOGGER.error("Discovery failed after %d attempts due to network error: %s", 
                                self._max_retries, e)
            except Exception as e:
                # Handle other unexpected errors
                last_exception = DiscoveryError(f"Unexpected error during discovery (attempt {attempt + 1}): {e}")
                if attempt < self._max_retries - 1:
                    backoff_time = self._base_backoff * (attempt + 1)
                    _LOGGER.warning("Discovery unexpected error on attempt %d: %s, retrying in %.2f seconds", 
                                  attempt + 1, e, backoff_time)
                    await asyncio.sleep(backoff_time)
                else:
                    _LOGGER.error("Discovery failed after %d attempts due to unexpected error: %s", 
                                self._max_retries, e)
        
        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise DiscoveryError(f"Discovery failed after {self._max_retries} attempts")

    def _parse_transponder_data(self, data: bytes) -> Dict[str, Any]:
        """Parse transponder XML data with improved error handling."""
        try:
            xml = ET.fromstring(data)
            info = {}
            
            # Extract basic device information
            for child in xml:
                if child.tag == "model":
                    info["model"] = child.text
                elif child.tag == "revision":
                    info["revision"] = child.text
                elif child.tag == "name":
                    info["name"] = child.text
                elif child.tag == "control":
                    # Extract information from the control element according to spec
                    for ctrl_child in child:
                        if ctrl_child.tag == "version":
                            # This is the correct protocol version as per spec
                            info["protocolVersion"] = ctrl_child.text
                            _LOGGER.debug("Protocol version: %s", ctrl_child.text)
                        elif ctrl_child.tag.endswith("Port"):
                            info[ctrl_child.tag] = int(ctrl_child.text)
                            _LOGGER.debug("Found port %s = %s", ctrl_child.tag, ctrl_child.text)
                        elif ctrl_child.tag == "keepAlive":
                            info["keepAlive"] = int(ctrl_child.text)
                            _LOGGER.debug("Found keepAlive = %s ms", ctrl_child.text)
                        else:
                            info[ctrl_child.tag] = ctrl_child.text
                else:
                    info[child.tag] = child.text
                    
            # Default to protocol version 2.0 if not specified
            if "protocolVersion" not in info:
                _LOGGER.warning("Protocol version not found in transponder, defaulting to 2.0")
                info["protocolVersion"] = "2.0"
                    
            _LOGGER.info("Device info: model=%s, name=%s, protocol=%s, ports=%s", 
                       info.get("model", "Unknown"), 
                       info.get("name", "Unknown"),
                       info.get("protocolVersion"), 
                       {k: v for k, v in info.items() if k.endswith("Port")})
            return info
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse transponder XML: %s", e)
            raise DiscoveryError(f"Invalid transponder XML: {e}") from e
