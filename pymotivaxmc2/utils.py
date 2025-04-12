"""
Utility functions for the eMotiva integration.

This module provides utility functions for handling network communication,
data formatting, and response parsing for Emotiva devices.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import xml.etree.ElementTree as ET
from .constants import NOTIFY_EVENTS

_LOGGER = logging.getLogger(__name__)

def format_request(command: str, params: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Format a request for the Emotiva device.
    
    Args:
        command: The command to send
        params: Optional parameters for the command
        
    Returns:
        Formatted request as bytes
    """
    # Special case for emotivaPing which is sent without wrapper
    if command == 'emotivaPing':
        root = ET.Element(command)
        # Add any parameters to the command element
        if params:
            for key, value in params.items():
                root.set(key, str(value))
    
    # Special case for subscription command
    elif command == 'emotivaSubscription':
        root = ET.Element(command)
        # Add subscription elements
        if params:
            for event_type, event_params in params.items():
                event_elem = ET.SubElement(root, event_type)
                if event_params:
                    for key, value in event_params.items():
                        event_elem.set(key, str(value))
    
    # Regular control commands
    elif command == 'emotivaControl':
        # For control wrapper, just create it and add sub-commands
        root = ET.Element(command)
        
        # Add command parameters as child elements
        if params:
            for cmd_name, cmd_params in params.items():
                cmd_elem = ET.SubElement(root, cmd_name)
                if isinstance(cmd_params, dict):
                    for key, value in cmd_params.items():
                        if isinstance(value, dict):
                            # Handle nested parameters
                            sub_elem = ET.SubElement(cmd_elem, key)
                            for sub_key, sub_value in value.items():
                                sub_elem.set(sub_key, str(sub_value))
                        else:
                            # Simple parameters as attributes
                            cmd_elem.set(key, str(value))
    
    # Simple commands - for legacy or direct commands
    else:
        # For other commands, wrap them in request
        root = ET.Element('Request')
        cmd_element = ET.SubElement(root, command)
        
        # Add any parameters to the command element
        if params:
            for key, value in params.items():
                if isinstance(value, dict):
                    # Handle nested parameters by creating child elements
                    param_element = ET.SubElement(cmd_element, key)
                    for sub_key, sub_value in value.items():
                        param_element.set(sub_key, str(sub_value))
                else:
                    # Simple parameters as attributes
                    cmd_element.set(key, str(value))
    
    # Convert to bytes and fix any XML formatting issues
    xml_string = ET.tostring(root, encoding='utf-8', short_empty_elements=True)
    
    # Fix the XML to ensure proper formatting (no extra spaces in self-closing tags)
    xml_string = xml_string.replace(b' />', b'/>')
    
    _LOGGER.debug("Formatted request: %s", xml_string.decode('utf-8'))
    return xml_string

def parse_response(data: bytes) -> Optional[ET.Element]:
    """
    Parse XML response data.
    
    Args:
        data (bytes): Raw XML response data
        
    Returns:
        Optional[ET.Element]: Parsed XML element or None if parsing fails
    """
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        _LOGGER.error("Failed to parse response: %s", e)
        return None

def validate_response(doc: ET.Element, expected_tag: str) -> bool:
    """
    Validate that a response has the expected tag.
    
    Args:
        doc (ET.Element): Parsed XML document
        expected_tag (str): Expected tag name
        
    Returns:
        bool: True if valid, False otherwise
    """
    if doc is None:
        _LOGGER.error("Response document is None")
        return False
        
    if expected_tag == "emotivaAck":
        if doc.tag != "emotivaAck":
            _LOGGER.error("Expected emotivaAck response, got %s", doc.tag)
            return False
    elif expected_tag == "emotivaTransponder":
        if doc.tag != "emotivaTransponder":
            _LOGGER.error("Expected emotivaTransponder response, got %s", doc.tag)
            return False
    elif expected_tag == "emotivaNotify":
        if doc.tag != "emotivaNotify":
            _LOGGER.error("Expected emotivaNotify response, got %s", doc.tag)
            return False
    elif expected_tag == "emotivaMenuNotify":
        if doc.tag != "emotivaMenuNotify":
            _LOGGER.error("Expected emotivaMenuNotify response, got %s", doc.tag)
            return False
    elif expected_tag == "emotivaBarNotify":
        if doc.tag != "emotivaBarNotify":
            _LOGGER.error("Expected emotivaBarNotify response, got %s", doc.tag)
            return False
    elif expected_tag == "Response":
        # Legacy format
        if doc.tag != "Response":
            _LOGGER.error("Expected Response response, got %s", doc.tag)
            return False
    else:
        # For other types of responses, match the tag directly
        if doc.tag != expected_tag:
            _LOGGER.error("Expected %s response, got %s", expected_tag, doc.tag)
            return False
            
    return True

def extract_command_response(doc: ET.Element, command: str) -> Optional[Dict[str, Any]]:
    """
    Extract command response data from a document.
    
    Args:
        doc (ET.Element): Parsed XML document
        command (str): Command name
        
    Returns:
        Optional[Dict[str, Any]]: Command response data or None if not found
    """
    # Check for emotivaAck format (protocol-compliant responses)
    if doc.tag == 'emotivaAck':
        cmd = doc.find(command)
        if cmd is None:
            _LOGGER.error("Command %s not found in emotivaAck response", command)
            return None
        
        return {k: v for k, v in cmd.attrib.items()}
    
    # Fallback for older response format
    elif doc.tag == 'Response':
        cmd = doc.find(command)
        if cmd is None:
            _LOGGER.error("Command %s not found in response", command)
            return None
        
        return {k: v for k, v in cmd.attrib.items()}
    
    # No valid response format found
    _LOGGER.error("Invalid response format: %s", doc.tag)
    return None
