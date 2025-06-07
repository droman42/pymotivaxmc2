"""Test cases for pymotivaxmc2.core.xmlcodec module."""

import pytest
import xml.etree.ElementTree as ET
from pymotivaxmc2.core.xmlcodec import (
    parse_xml,
    build_command,
    build_update,
    build_subscribe,
    build_unsubscribe,
)


class TestParseXml:
    """Test cases for parse_xml function."""

    def test_parse_valid_xml(self):
        """Test parsing valid XML bytes."""
        xml_data = b'<root><child>value</child></root>'
        result = parse_xml(xml_data)
        
        assert result.tag == "root"
        assert len(result) == 1
        assert result[0].tag == "child"
        assert result[0].text == "value"

    def test_parse_xml_with_attributes(self):
        """Test parsing XML with attributes."""
        xml_data = b'<emotivaNotify><power visible="true" value="On">On</power></emotivaNotify>'
        result = parse_xml(xml_data)
        
        assert result.tag == "emotivaNotify"
        power_elem = result[0]
        assert power_elem.tag == "power"
        assert power_elem.get("visible") == "true"
        assert power_elem.get("value") == "On"
        assert power_elem.text == "On"

    def test_parse_empty_xml_element(self):
        """Test parsing XML with empty elements."""
        xml_data = b'<emotivaSubscription><power/><volume/></emotivaSubscription>'
        result = parse_xml(xml_data)
        
        assert result.tag == "emotivaSubscription"
        assert len(result) == 2
        assert result[0].tag == "power"
        assert result[1].tag == "volume"

    def test_parse_invalid_xml(self):
        """Test that invalid XML raises ParseError."""
        invalid_xml = b'<root><unclosed_tag></root>'
        
        with pytest.raises(ET.ParseError):
            parse_xml(invalid_xml)

    def test_parse_non_xml_data(self):
        """Test that non-XML data raises ParseError."""
        non_xml = b'This is not XML'
        
        with pytest.raises(ET.ParseError):
            parse_xml(non_xml)

    def test_parse_xml_with_encoding(self):
        """Test parsing XML with special characters."""
        xml_data = '<?xml version="1.0" encoding="utf-8"?><root>Ñoñó</root>'.encode('utf-8')
        result = parse_xml(xml_data)
        
        assert result.tag == "root"
        assert result.text == "Ñoñó"


class TestBuildCommand:
    """Test cases for build_command function."""

    def test_build_simple_command(self):
        """Test building a simple command without attributes."""
        result = build_command("power_on")
        
        # Parse the result to verify structure
        root = ET.fromstring(result)
        assert root.tag == "emotivaControl"
        assert len(root) == 1
        
        cmd_elem = root[0]
        assert cmd_elem.tag == "power_on"
        assert cmd_elem.get("value") == "0"  # Default value
        assert cmd_elem.get("ack") == "yes"  # Default ack

    def test_build_command_with_attributes(self):
        """Test building a command with custom attributes."""
        result = build_command("set_volume", value="-20.5", ack="yes")
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaControl"
        
        cmd_elem = root[0]
        assert cmd_elem.tag == "set_volume"
        assert cmd_elem.get("value") == "-20.5"
        assert cmd_elem.get("ack") == "yes"

    def test_build_command_protocol_versions(self):
        """Test building commands with different protocol versions."""
        # Protocol version doesn't affect command structure but parameter should be accepted
        result_v2 = build_command("power_on", protocol_version="2.0")
        result_v3 = build_command("power_on", protocol_version="3.1")
        
        # Both should produce valid XML
        root_v2 = ET.fromstring(result_v2)
        root_v3 = ET.fromstring(result_v3)
        
        assert root_v2.tag == "emotivaControl"
        assert root_v3.tag == "emotivaControl"

    def test_build_command_custom_attributes(self):
        """Test building command with multiple custom attributes."""
        result = build_command("test_cmd", value="100", custom="attr", another="value")
        
        root = ET.fromstring(result)
        cmd_elem = root[0]
        
        assert cmd_elem.get("value") == "100"
        assert cmd_elem.get("custom") == "attr"
        assert cmd_elem.get("another") == "value"
        assert cmd_elem.get("ack") == "yes"  # Should still have default ack

    def test_build_command_returns_bytes(self):
        """Test that build_command returns bytes."""
        result = build_command("power_on")
        assert isinstance(result, bytes)

    def test_build_command_includes_xml_declaration(self):
        """Test that the result includes XML declaration."""
        result = build_command("power_on")
        result_str = result.decode('utf-8')
        assert result_str.startswith('<?xml version="1.0" encoding="utf-8"?>')


class TestBuildUpdate:
    """Test cases for build_update function."""

    def test_build_update_single_property(self):
        """Test building update request for single property."""
        result = build_update(["power"])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUpdate"
        assert len(root) == 1
        assert root[0].tag == "power"

    def test_build_update_multiple_properties(self):
        """Test building update request for multiple properties."""
        properties = ["power", "volume", "mute"]
        result = build_update(properties)
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUpdate"
        assert len(root) == 3
        
        property_tags = [elem.tag for elem in root]
        assert property_tags == properties

    def test_build_update_empty_list(self):
        """Test building update request with empty property list."""
        result = build_update([])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUpdate"
        assert len(root) == 0

    def test_build_update_protocol_v2(self):
        """Test building update with protocol version 2.0."""
        result = build_update(["power"], protocol_version="2.0")
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUpdate"
        assert root.get("protocol") is None  # No protocol attribute for v2.0

    def test_build_update_protocol_v3(self):
        """Test building update with protocol version 3.0+."""
        result = build_update(["power"], protocol_version="3.1")
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUpdate"
        assert root.get("protocol") == "3.1"

    def test_build_update_returns_bytes(self):
        """Test that build_update returns bytes."""
        result = build_update(["power"])
        assert isinstance(result, bytes)


class TestBuildSubscribe:
    """Test cases for build_subscribe function."""

    def test_build_subscribe_single_property(self):
        """Test building subscription for single property."""
        result = build_subscribe(["power"])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaSubscription"
        assert len(root) == 1
        assert root[0].tag == "power"

    def test_build_subscribe_multiple_properties(self):
        """Test building subscription for multiple properties."""
        properties = ["power", "volume", "mute", "input"]
        result = build_subscribe(properties)
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaSubscription"
        assert len(root) == 4
        
        property_tags = [elem.tag for elem in root]
        assert property_tags == properties

    def test_build_subscribe_empty_list(self):
        """Test building subscription with empty property list."""
        result = build_subscribe([])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaSubscription"
        assert len(root) == 0

    def test_build_subscribe_protocol_v2(self):
        """Test building subscription with protocol version 2.0."""
        result = build_subscribe(["power"], protocol_version="2.0")
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaSubscription"
        assert root.get("protocol") is None  # No protocol attribute for v2.0

    def test_build_subscribe_protocol_v3(self):
        """Test building subscription with protocol version 3.0+."""
        result = build_subscribe(["power"], protocol_version="3.1")
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaSubscription"
        assert root.get("protocol") == "3.1"

    def test_build_subscribe_returns_bytes(self):
        """Test that build_subscribe returns bytes."""
        result = build_subscribe(["power"])
        assert isinstance(result, bytes)


class TestBuildUnsubscribe:
    """Test cases for build_unsubscribe function."""

    def test_build_unsubscribe_single_property(self):
        """Test building unsubscription for single property."""
        result = build_unsubscribe(["power"])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUnsubscribe"
        assert len(root) == 1
        assert root[0].tag == "power"

    def test_build_unsubscribe_multiple_properties(self):
        """Test building unsubscription for multiple properties."""
        properties = ["power", "volume", "mute"]
        result = build_unsubscribe(properties)
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUnsubscribe"
        assert len(root) == 3
        
        property_tags = [elem.tag for elem in root]
        assert property_tags == properties

    def test_build_unsubscribe_empty_list(self):
        """Test building unsubscription with empty property list."""
        result = build_unsubscribe([])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUnsubscribe"
        assert len(root) == 0

    def test_build_unsubscribe_no_protocol_attribute(self):
        """Test that unsubscribe doesn't include protocol attribute."""
        result = build_unsubscribe(["power"])
        
        root = ET.fromstring(result)
        assert root.tag == "emotivaUnsubscribe"
        assert root.get("protocol") is None  # Never has protocol attribute

    def test_build_unsubscribe_returns_bytes(self):
        """Test that build_unsubscribe returns bytes."""
        result = build_unsubscribe(["power"])
        assert isinstance(result, bytes)


class TestXmlCodecIntegration:
    """Integration tests for XML codec functions."""

    def test_build_and_parse_command(self):
        """Test building a command and parsing it back."""
        # Build command
        xml_bytes = build_command("power_on", value="1", ack="yes")
        
        # Parse it back
        root = parse_xml(xml_bytes)
        
        assert root.tag == "emotivaControl"
        cmd_elem = root[0]
        assert cmd_elem.tag == "power_on"
        assert cmd_elem.get("value") == "1"
        assert cmd_elem.get("ack") == "yes"

    def test_build_and_parse_subscription(self):
        """Test building a subscription and parsing it back."""
        properties = ["power", "volume", "mute"]
        
        # Build subscription
        xml_bytes = build_subscribe(properties, protocol_version="3.1")
        
        # Parse it back
        root = parse_xml(xml_bytes)
        
        assert root.tag == "emotivaSubscription"
        assert root.get("protocol") == "3.1"
        assert len(root) == 3
        assert [elem.tag for elem in root] == properties

    def test_xml_encoding_consistency(self):
        """Test that all build functions produce consistent encoding."""
        functions_and_args = [
            (build_command, ("power_on",)),
            (build_update, (["power"],)),
            (build_subscribe, (["power"],)),
            (build_unsubscribe, (["power"],)),
        ]
        
        for func, args in functions_and_args:
            result = func(*args)
            
            # Should be bytes
            assert isinstance(result, bytes)
            
            # Should start with XML declaration
            result_str = result.decode('utf-8')
            assert result_str.startswith('<?xml version="1.0" encoding="utf-8"?>')
            
            # Should be parseable
            parsed = parse_xml(result)
            assert parsed is not None 