"""
Utility functions for working with Emotiva device communication.

This module contains utility functions for formatting requests,
parsing responses, and general XML handling for Emotiva A/V devices.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List, Union, cast

_LOGGER = logging.getLogger(__name__)

def format_request(command: str, params: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Format a command request as XML.
    
    Args:
        command (str): Command name
        params (dict, optional): Command parameters
    
    Returns:
        bytes: Formatted XML request
    """
    # Create the root element based on the command type
    if command == 'emotivaPing':
        root = ET.Element('emotivaPing')
    elif command == 'emotivaAck':
        root = ET.Element('emotivaAck')
    elif command == 'emotivaNotify':
        root = ET.Element('emotivaNotify')
    elif command == 'emotivaMenuNotify':
        root = ET.Element('emotivaMenuNotify')
    elif command == 'emotivaBarNotify':
        root = ET.Element('emotivaBarNotify')
    elif command == 'emotivaSubscribe':
        root = ET.Element('emotivaSubscribe')
    elif command == 'emotivaTransponder':
        root = ET.Element('emotivaTransponder')
    else:
        # For regular commands, use the emotivaSend root
        root = ET.Element('emotivaSend')
        
    # If parameters are provided, add them to the request
    if params:
        # For the ping request, parameters are direct attributes of the root
        if command == 'emotivaPing':
            for key, value in params.items():
                root.set(key, str(value))
        elif command == 'emotivaSubscribe':
            # For subscription requests, handle the events list
            if 'events' in params and isinstance(params['events'], list):
                events = params['events']
                for event in events:
                    event_element = ET.SubElement(root, 'event')
                    event_element.set('type', event)
            
            # Add other subscription parameters as attributes
            for key, value in params.items():
                if key != 'events':
                    root.set(key, str(value))
        else:
            # For regular commands, create a command element
            cmd_element = ET.SubElement(root, command)
            
            # Process parameters for the command
            for key, value in params.items():
                if isinstance(value, dict):
                    # Nested parameters as sub-elements
                    param_element = ET.SubElement(cmd_element, key)
                    for sub_key, sub_value in value.items():
                        param_element.set(sub_key, str(sub_value))
                elif isinstance(value, list):
                    # List parameters as multiple sub-elements
                    for item in value:
                        if isinstance(item, dict):
                            list_element = ET.SubElement(cmd_element, key)
                            for item_key, item_value in item.items():
                                list_element.set(item_key, str(item_value))
                        else:
                            list_element = ET.SubElement(cmd_element, key)
                            list_element.text = str(item)
                else:
                    # Simple parameters as attributes
                    cmd_element.set(key, str(value))
    
    # Convert to bytes and fix any XML formatting issues
    xml_string = ET.tostring(root, encoding='utf-8', short_empty_elements=True)
    
    # Fix the XML to ensure proper formatting (no extra spaces in self-closing tags)
    xml_string = xml_string.replace(b' />', b'/>')
    
    _LOGGER.debug("Formatted request: %s", xml_string.decode('utf-8'))
    return cast(bytes, xml_string)

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
