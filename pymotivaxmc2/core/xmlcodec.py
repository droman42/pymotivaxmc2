"""Creates & parses XML protocol messages."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from xml.etree.ElementTree import Element

from .logging import get_logger

# Module logger
_LOGGER = get_logger("xmlcodec")

def parse_xml(data: bytes) -> Element:
    """Parse XML from bytes into element."""
    try:
        xml = ET.fromstring(data)
        _LOGGER.debug("Parsed XML tag: %s", xml.tag)
        return xml
    except ET.ParseError as e:
        _LOGGER.error("Failed to parse XML: %s", e)
        _LOGGER.debug("Invalid XML data: %s", data.decode('utf-8', errors='replace'))
        raise

def build_command(name: str, protocol_version: str = "2.0", **attributes: Any) -> bytes:
    """Build a command XML message."""
    _LOGGER.debug("Building command XML: %s with attributes %s", name, attributes)
    cmd = ET.Element("emotivaControl")
    
    # Technically the protocol version is not needed in command packets according to the spec,
    # but we're keeping the parameter for consistency with other methods
    
    sub = ET.SubElement(cmd, name)
    
    # Always ensure we have a value attribute as required by the protocol spec
    if "value" not in attributes:
        attributes["value"] = "0"
    
    # Always ensure we have an ack attribute as shown in the spec examples
    if "ack" not in attributes:
        attributes["ack"] = "yes"
        
    for key, value in attributes.items():
        sub.set(key, str(value))
        
    xml_str = '<?xml version="1.0" encoding="utf-8"?>'
    return (xml_str + ET.tostring(cmd, encoding='unicode')).encode('utf-8')

def build_update(properties: list[str], protocol_version: str = "2.0") -> bytes:
    """Build an update request for the specified properties."""
    _LOGGER.debug("Building update XML for properties: %s (protocol %s)", 
                properties, protocol_version)
    elem = ET.Element("emotivaUpdate")
    
    # Add protocol attribute for V3.0+
    if protocol_version >= "3.0":
        elem.set("protocol", protocol_version)
    
    for name in properties:
        prop = ET.SubElement(elem, name)
        
    xml_str = '<?xml version="1.0" encoding="utf-8"?>'
    return (xml_str + ET.tostring(elem, encoding='unicode')).encode('utf-8')

def build_subscribe(properties: list[str], protocol_version: str = "2.0") -> bytes:
    """Build a subscription request for the specified properties."""
    _LOGGER.debug("Building subscription XML for properties: %s (protocol %s)", 
                properties, protocol_version)
    elem = ET.Element("emotivaSubscription")
    
    # Add protocol attribute for V3.0+
    if protocol_version >= "3.0":
        elem.set("protocol", protocol_version)
    
    for name in properties:
        prop = ET.SubElement(elem, name)
        
    xml_str = '<?xml version="1.0" encoding="utf-8"?>'
    return (xml_str + ET.tostring(elem, encoding='unicode')).encode('utf-8')

def build_unsubscribe(properties: list[str]) -> bytes:
    """Build an unsubscribe request for the specified properties."""
    _LOGGER.debug("Building unsubscribe XML for properties: %s", properties)
    elem = ET.Element("emotivaUnsubscribe")
    
    # The unsubscribe message doesn't require a protocol version attribute
    # according to the specification
    
    for name in properties:
        prop = ET.SubElement(elem, name)
        
    xml_str = '<?xml version="1.0" encoding="utf-8"?>'
    return (xml_str + ET.tostring(elem, encoding='unicode')).encode('utf-8')
