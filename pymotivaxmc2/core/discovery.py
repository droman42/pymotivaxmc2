"""Performs unicast discovery ping to obtain transponder XML."""
from __future__ import annotations

import asyncio
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
        _LOGGER.debug("Discovery initialized for host %s (timeout=%.1f)", host, timeout)

    async def fetch_transponder(self) -> Dict[str, Any]:
        """Send ping to port 7000 and wait for transponder on 7001."""
        _LOGGER.info("Discovering device at %s", self.host)
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

        try:
            _LOGGER.debug("Binding to port 7001 for transponder response")
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _Proto(),
                local_addr=("0.0.0.0", 7001),
            )
            
            _LOGGER.debug("Sending ping to %s:7000", self.host)
            log_xml(_LOGGER, "sent", PING_XML)
            transport.sendto(PING_XML, (self.host, 7000))

            try:
                _LOGGER.debug("Waiting for transponder response (timeout=%.1f)", self.timeout)
                data = await asyncio.wait_for(recv_fut, timeout=self.timeout)
                _LOGGER.info("Received transponder response from %s", self.host)
            except asyncio.TimeoutError as e:
                _LOGGER.error("No transponder reply from %s after %.1f seconds", self.host, self.timeout)
                raise DiscoveryError("No transponder reply") from e
        finally:
            transport.close()

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
