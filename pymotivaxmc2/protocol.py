"""
Protocol Module for Emotiva Integration.

This module provides classes for handling the Emotiva protocol, including
command formatting, response parsing, and protocol version compatibility.
"""

import logging
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import re
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Union, Tuple, cast

from .constants import (
    MODE_PRESETS,
    PROTOCOL_VERSION,
    REQUEST_TYPES,
    RESPONSE_TYPES,
)
from .emotiva_types import (
    EmotivaNotification,
    NotificationType,
    ConnectionState,
    BarNotification,
)
from .exceptions import (
    EmotivaError,
    InvalidModeError,
    InvalidResponseError,
    InvalidSourceError,
    InvalidTransponderResponseError,
    InvalidCommandResponseError,
    InvalidNotificationError
)

_LOGGER = logging.getLogger(__name__)


class TransponderResponse:
    """Represents a response from a device transponder."""
    
    def __init__(self, data: Dict[str, Any]):
        """
        Initialize a transponder response.
        
        Args:
            data: Data from the transponder response
        """
        self.name = data.get("name", "")
        self.model = data.get("model", "")
        self.version = data.get("protocol", "1.0")
        
        # Extract ports
        self.ports = {}
        ports_data = data.get("ports", {})
        if isinstance(ports_data, dict):
            for port_name, port_value in ports_data.items():
                try:
                    self.ports[port_name] = int(port_value)
                except (ValueError, TypeError):
                    pass
        
        # Extract keepalive interval
        self.keepalive_interval = None
        try:
            if "keepaliveInterval" in data:
                self.keepalive_interval = int(data["keepaliveInterval"])
        except (ValueError, TypeError):
            pass


class ProtocolVersion:
    """
    Handles protocol version compatibility.
    
    This class provides methods for comparing protocol versions and ensuring
    backward compatibility.
    """
    
    @staticmethod
    def parse_version(version_str: str) -> Tuple[int, int]:
        """
        Parse a protocol version string into major and minor components.
        
        Args:
            version_str: Version string (e.g., "1.2")
            
        Returns:
            Tuple[int, int]: Major and minor version numbers
        """
        try:
            major, minor = version_str.split('.')
            return int(major), int(minor)
        except (ValueError, AttributeError):
            # Default to 1.0 if parsing fails
            return 1, 0
    
    @staticmethod
    def is_compatible(device_version: str, required_version: str) -> bool:
        """
        Check if a device protocol version is compatible with a required version.
        
        Args:
            device_version: Device protocol version
            required_version: Minimum required version
            
        Returns:
            bool: True if compatible
        """
        device_major, device_minor = ProtocolVersion.parse_version(device_version)
        required_major, required_minor = ProtocolVersion.parse_version(required_version)
        
        # Major version must match, minor version must be >= required
        return (device_major == required_major and device_minor >= required_minor)
        
    @staticmethod
    def latest() -> str:
        """
        Get the latest supported protocol version.
        
        Returns:
            str: Latest protocol version
        """
        return PROTOCOL_VERSION


class EmotivaCommand:
    """
    Represents a command to send to an Emotiva device.
    
    This class encapsulates a command and its parameters for sending
    to an Emotiva device.
    """
    
    def __init__(
        self, command_type: str, 
        params: Optional[Dict[str, Any]] = None,
        ack: bool = False
    ):
        """
        Initialize a command.
        
        Args:
            command_type: Type of command
            params: Command parameters
            ack: Whether an acknowledgment is requested
        """
        self.command_type = command_type
        self.params = params or {}
        self.ack = ack
    
    def to_xml(self, protocol_version: Optional[str] = None) -> str:
        """
        Convert the command to XML.
        
        Args:
            protocol_version: Protocol version to use
            
        Returns:
            str: XML representation of the command
        """
        return CommandFormatter.format_request(
            self.command_type,
            self.params,
            protocol_version
        )


class CommandFormatter:
    """
    Formats commands in the Emotiva protocol format.
    
    This class provides methods for formatting commands as XML according
    to the Emotiva protocol.
    """
    
    @staticmethod
    def format_request(
        command_type: str, 
        params: Optional[Dict[str, Any]] = None,
        protocol_version: Optional[str] = None
    ) -> str:
        """
        Format a request as XML according to the Emotiva protocol.
        
        Args:
            command_type: Type of command (e.g., "discover", "control")
            params: Command parameters
            protocol_version: Protocol version to use
            
        Returns:
            str: Formatted XML request
        """
        if protocol_version is None:
            protocol_version = PROTOCOL_VERSION
            
        if params is None:
            params = {}
            
        # Create root element
        root = ET.Element(command_type)
        
        # Add protocol version if it's a discover request
        if command_type == "discover":
            root.set("protocol", protocol_version)
            
        # Add parameters
        for key, value in params.items():
            if isinstance(value, list):
                # Handle list parameters
                list_elem = ET.SubElement(root, key)
                for item in value:
                    if isinstance(item, dict):
                        # Handle dictionary items
                        item_elem = ET.SubElement(list_elem, "item")
                        for item_key, item_value in item.items():
                            item_elem.set(item_key, str(item_value))
                    else:
                        # Handle simple items
                        item_elem = ET.SubElement(list_elem, "item")
                        item_elem.text = str(item)
            elif isinstance(value, dict):
                # Handle dictionary parameters
                dict_elem = ET.SubElement(root, key)
                for dict_key, dict_value in value.items():
                    dict_elem.set(dict_key, str(dict_value))
            else:
                # Handle simple parameters
                root.set(key, str(value))
                
        # Convert to string
        xml_str = ET.tostring(root, encoding='utf-8').decode('utf-8')
        
        # Pretty-print for debugging
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
        
        # Remove XML declaration and extra whitespace
        pretty_xml = '\n'.join(line for line in pretty_xml.split('\n')
                              if line.strip() and not line.startswith('<?xml'))
        
        return pretty_xml.strip()
    
    @staticmethod
    def format_control_request(command: str, value: str, ack: bool = False) -> str:
        """
        Format a control request.
        
        Args:
            command: Control command
            value: Command value
            ack: Whether to request acknowledgment
            
        Returns:
            str: Formatted control request
        """
        params = {
            "command": command,
            "value": value
        }
        
        if ack:
            params["ack"] = "true"
            
        return CommandFormatter.format_request("control", params)
            
    @staticmethod
    def format_ping_request(protocol_version: Optional[str] = None) -> bytes:
        """
        Format a ping request for device discovery.
        
        Args:
            protocol_version: Protocol version to use
            
        Returns:
            bytes: Formatted ping request
        """
        if protocol_version is None:
            protocol_version = PROTOCOL_VERSION
            
        discover_xml = CommandFormatter.format_request("discover", {"ping": "true"}, protocol_version)
        return discover_xml.encode('utf-8')


class ResponseParser:
    """
    Parses responses from Emotiva devices.
    
    This class provides methods for parsing XML responses from Emotiva
    devices into structured data.
    """
    
    @staticmethod
    def parse_response(xml_data: bytes) -> Dict[str, Any]:
        """
        Parse an XML response into a structured object.
        
        Args:
            xml_data: XML response data
            
        Returns:
            Dict[str, Any]: Parsed response
            
        Raises:
            InvalidTransponderResponseError: If the response is invalid
        """
        try:
            # Parse XML
            xml_str = xml_data.decode('utf-8', errors='ignore')
            root = ET.fromstring(xml_str)
            
            # Get response type
            response_type = root.tag
            
            if response_type not in RESPONSE_TYPES:
                raise InvalidTransponderResponseError(f"Unknown response type: {response_type}")
                
            # Handle different response types
            if response_type == "transponder":
                return ResponseParser._parse_transponder_response(root)
            elif response_type == "command":
                return ResponseParser._parse_command_response(root)
            elif response_type == "notify":
                return ResponseParser._parse_notification_response(root)
            elif response_type == "error":
                return ResponseParser._parse_error_response(root)
                
            # Should never get here due to check above
            return {"status": "error", "message": f"Unknown response type: {response_type}"}
            
        except ET.ParseError as e:
            raise InvalidTransponderResponseError(f"Invalid XML: {e}")
        except Exception as e:
            raise InvalidTransponderResponseError(f"Error parsing response: {e}")
    
    @staticmethod
    def _parse_transponder_response(root: ET.Element) -> Dict[str, Any]:
        """
        Parse a transponder response.
        
        Args:
            root: XML root element
            
        Returns:
            Dict[str, Any]: Parsed response
        """
        result = {
            "status": "ok",
            "type": "transponder",
            "data": {}
        }
        
        # Extract attributes
        for key, value in root.attrib.items():
            result["data"][key] = value
            
        # Extract child elements
        for child in root:
            if len(child) > 0 or child.attrib:
                # Complex element
                child_data = {}
                
                # Add attributes
                for key, value in child.attrib.items():
                    child_data[key] = value
                
                # Add children
                for grandchild in child:
                    if grandchild.tag not in child_data:
                        child_data[grandchild.tag] = []
                    
                    if grandchild.attrib:
                        child_data[grandchild.tag].append(grandchild.attrib)
                    elif grandchild.text:
                        child_data[grandchild.tag].append(grandchild.text)
                
                result["data"][child.tag] = child_data
            elif child.text:
                # Simple element with text
                result["data"][child.tag] = child.text
            else:
                # Empty element
                result["data"][child.tag] = ""
                
        return result
    
    @staticmethod
    def _parse_command_response(root: ET.Element) -> Dict[str, Any]:
        """
        Parse a command response.
        
        Args:
            root: XML root element
            
        Returns:
            Dict[str, Any]: Parsed response
        """
        result = {
            "status": "ok",
            "type": "command",
            "data": {}
        }
        
        # Extract attributes
        for key, value in root.attrib.items():
            if key == "status":
                result["status"] = value
            else:
                result["data"][key] = value
        
        return result
    
    @staticmethod
    def _parse_notification_response(root: ET.Element) -> Dict[str, Any]:
        """
        Parse a notification response.
        
        Args:
            root: XML root element
            
        Returns:
            Dict[str, Any]: Parsed response
        """
        result = {
            "status": "ok",
            "type": "notify",
            "data": {}
        }
        
        # Extract notification type
        notify_type = root.get("type")
        if notify_type:
            result["data"]["notify_type"] = notify_type
            
        # Extract properties
        if notify_type == "property":
            properties = {}
            
            for child in root:
                if child.tag == "properties":
                    for prop in child:
                        prop_name = prop.get("name")
                        if prop_name:
                            prop_data = {"value": prop.get("value", "")}
                            
                            # Add other attributes
                            for key, value in prop.attrib.items():
                                if key != "name" and key != "value":
                                    prop_data[key] = value
                                    
                            properties[prop_name] = prop_data
            
            result["data"]["properties"] = properties
            
        # Extract menu data
        elif notify_type == "menu":
            menu_data = {
                "menu_id": root.get("id", ""),
                "position": int(root.get("position", "0")),
                "items": []
            }
            
            # Extract menu items
            for child in root:
                if child.tag == "items":
                    for item in child:
                        item_data = {}
                        
                        # Add attributes
                        for key, value in item.attrib.items():
                            item_data[key] = value
                            
                        menu_data["items"].append(item_data)
            
            result["data"].update(menu_data)
            
        # Extract bar data
        elif notify_type == "bar":
            bars = []
            
            for child in root:
                if child.tag == "bar":
                    bar_data = {}
                    
                    # Add attributes
                    for key, value in child.attrib.items():
                        bar_data[key] = value
                        
                    bars.append(bar_data)
            
            result["data"]["bars"] = bars
            
        return result
    
    @staticmethod
    def _parse_error_response(root: ET.Element) -> Dict[str, Any]:
        """
        Parse an error response.
        
        Args:
            root: XML root element
            
        Returns:
            Dict[str, Any]: Parsed response
        """
        result = {
            "status": "error",
            "type": "error",
            "message": root.get("message", "Unknown error")
        }
        
        # Extract error code if available
        if "code" in root.attrib:
            code = root.get("code")
            if code is not None:
                result["code"] = code
            
        return result
            
    @staticmethod
    def parse_transponder_response(response_doc: Dict[str, Any]) -> Optional[TransponderResponse]:
        """
        Parse a transponder response document into a structured object.
        
        Args:
            response_doc: Response document
            
        Returns:
            Optional[TransponderResponse]: Parsed transponder response
        """
        if not response_doc or response_doc.get("type") != "transponder":
            return None
            
        data = response_doc.get("data", {})
        
        return TransponderResponse(data) 