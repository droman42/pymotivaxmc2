"""
Utility functions for the eMotiva integration.

This module provides utility functions for handling network communication,
data formatting, and response parsing for Emotiva devices.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import xml.etree.ElementTree as ET

_LOGGER = logging.getLogger(__name__)

def format_request(command: str, params: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Format a command request as XML.
    
    Args:
        command (str): Command name
        params (Optional[Dict[str, Any]]): Command parameters
        
    Returns:
        bytes: Formatted XML request
    """
    root = ET.Element("Request")
    cmd = ET.SubElement(root, command)
    
    if params:
        for key, value in params.items():
            cmd.set(key, str(value))
            
    return ET.tostring(root, encoding="utf-8")

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
    Validate a response document.
    
    Args:
        doc (ET.Element): Parsed XML document
        expected_tag (str): Expected root tag name
        
    Returns:
        bool: True if the document is valid
    """
    if doc is None or doc.tag != expected_tag:
        _LOGGER.error("Invalid response format: expected %s, got %s",
                     expected_tag, doc.tag if doc else "None")
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
    if not validate_response(doc, "Response"):
        return None
        
    cmd = doc.find(command)
    if cmd is None:
        _LOGGER.error("Command %s not found in response", command)
        return None
        
    return {k: v for k, v in cmd.attrib.items()}
