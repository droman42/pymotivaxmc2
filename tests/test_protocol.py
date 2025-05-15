"""
Tests for the protocol module.
"""

import unittest
import xml.etree.ElementTree as ET
from typing import cast
from pymotivaxmc2.protocol import (
    CommandFormatter,
    ResponseParser,
    ProtocolVersion,
    EmotivaCommand,
    EmotivaResponse,
    CommandResponse,
    NotifyResponse,
    MenuNotifyResponse,
    BarNotifyResponse,
    TransponderResponse
)


class TestProtocolVersion(unittest.TestCase):
    """Test the ProtocolVersion class."""
    
    def test_from_string(self):
        """Test conversion from string to ProtocolVersion."""
        self.assertEqual(ProtocolVersion.from_string("1.0"), ProtocolVersion.V1_0)
        self.assertEqual(ProtocolVersion.from_string("2.0"), ProtocolVersion.V2_0)
        self.assertEqual(ProtocolVersion.from_string("3.1"), ProtocolVersion.V3_1)
        # Test with unknown version
        self.assertEqual(ProtocolVersion.from_string("4.0"), ProtocolVersion.V3_1)
    
    def test_is_at_least(self):
        """Test version comparison."""
        self.assertTrue(ProtocolVersion.V3_1.is_at_least(ProtocolVersion.V1_0))
        self.assertTrue(ProtocolVersion.V3_1.is_at_least(ProtocolVersion.V3_0))
        self.assertTrue(ProtocolVersion.V3_1.is_at_least(ProtocolVersion.V3_1))
        self.assertFalse(ProtocolVersion.V1_0.is_at_least(ProtocolVersion.V2_0))
    
    def test_latest(self):
        """Test getting the latest version."""
        self.assertEqual(ProtocolVersion.latest(), ProtocolVersion.V3_1)


class TestEmotivaCommand(unittest.TestCase):
    """Test the EmotivaCommand class."""
    
    def test_init(self):
        """Test initialization."""
        cmd = EmotivaCommand("volume", 10, True)
        self.assertEqual(cmd.name, "volume")
        self.assertEqual(cmd.value, 10)
        self.assertTrue(cmd.ack)
        self.assertEqual(cmd.parameters, {})
        
        # Test with parameters
        cmd = EmotivaCommand("volume", 10, True, {"zone": 1})
        self.assertEqual(cmd.parameters, {"zone": 1})
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        cmd = EmotivaCommand("volume", 10, True, {"zone": 1})
        cmd_dict = cmd.to_dict()
        self.assertEqual(cmd_dict["value"], "10")
        self.assertEqual(cmd_dict["ack"], "yes")
        self.assertEqual(cmd_dict["zone"], 1)
        
        # Test with ack=False
        cmd = EmotivaCommand("volume", 10, False)
        cmd_dict = cmd.to_dict()
        self.assertEqual(cmd_dict["ack"], "no")


class TestCommandFormatter(unittest.TestCase):
    """Test the CommandFormatter class."""
    
    def test_format_request(self):
        """Test formatting requests."""
        # Test simple ping request
        ping_req = CommandFormatter.format_request("emotivaPing")
        self.assertIn(b"<emotivaPing/>", ping_req)
        
        # Test ping with protocol version
        ping_req = CommandFormatter.format_request("emotivaPing", {"protocol": "3.1"})
        self.assertIn(b'<emotivaPing protocol="3.1"/>', ping_req)
        
        # Test control request
        control_req = CommandFormatter.format_request("emotivaControl", {
            "commands": [{
                "name": "volume",
                "params": {"value": "10", "ack": "yes"}
            }]
        })
        self.assertIn(b'<emotivaControl>', control_req)
        self.assertIn(b'<volume value="10" ack="yes"/>', control_req)
    
    def test_format_control_request(self):
        """Test formatting control requests."""
        # Test string command
        control_req = CommandFormatter.format_control_request("volume", "10")
        self.assertIn(b'<emotivaControl>', control_req)
        self.assertIn(b'<volume value="10" ack="yes"/>', control_req)
        
        # Test with no ack
        control_req = CommandFormatter.format_control_request("volume", "10", False)
        self.assertIn(b'<volume value="10" ack="no"/>', control_req)
        
        # Test with EmotivaCommand
        cmd = EmotivaCommand("volume", 10, True, {"zone": 1})
        control_req = CommandFormatter.format_control_request(cmd)
        self.assertIn(b'<volume value="10" ack="yes" zone="1"/>', control_req)
    
    def test_format_ping_request(self):
        """Test formatting ping requests."""
        ping_req = CommandFormatter.format_ping_request()
        self.assertIn(b"<emotivaPing/>", ping_req)
        
        # Test with protocol version
        ping_req = CommandFormatter.format_ping_request("3.1")
        self.assertIn(b'<emotivaPing protocol="3.1"/>', ping_req)
        
        # Test with ProtocolVersion enum
        ping_req = CommandFormatter.format_ping_request(ProtocolVersion.V3_1)
        self.assertIn(b'<emotivaPing protocol="3.1"/>', ping_req)
    
    def test_format_subscribe_request(self):
        """Test formatting subscription requests."""
        sub_req = CommandFormatter.format_subscribe_request(["power", "volume"])
        self.assertIn(b"<emotivaSubscribe>", sub_req)
        self.assertIn(b"<power/>", sub_req)
        self.assertIn(b"<volume/>", sub_req)
        
        # Test with protocol version
        sub_req = CommandFormatter.format_subscribe_request(["power"], "3.1")
        self.assertIn(b'<emotivaSubscribe protocol="3.1">', sub_req)
    
    def test_format_unsubscribe_request(self):
        """Test formatting unsubscription requests."""
        unsub_req = CommandFormatter.format_unsubscribe_request(["power", "volume"])
        self.assertIn(b"<emotivaUnsubscribe>", unsub_req)
        self.assertIn(b"<power/>", unsub_req)
        self.assertIn(b"<volume/>", unsub_req)


class TestResponseParser(unittest.TestCase):
    """Test the ResponseParser class."""
    
    def test_parse_response(self):
        """Test parsing XML responses."""
        xml_data = b'<?xml version="1.0" encoding="utf-8"?><emotivaAck><volume status="ack"/></emotivaAck>'
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            self.assertEqual(doc.tag, "emotivaAck")
        
        # Test with invalid XML
        xml_data = b'<invalid XML>'
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNone(doc)
    
    def test_parse_command_response(self):
        """Test parsing command responses."""
        xml_data = b'<?xml version="1.0" encoding="utf-8"?><emotivaAck><volume status="ack"/></emotivaAck>'
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_command_response(cast(ET.Element, doc), "volume")
            self.assertIsNotNone(response)
            if response is not None:
                self.assertEqual(response.status, "ack")
                self.assertEqual(response.command, "volume")
        
            # Test with no matching command
            response = ResponseParser.parse_command_response(cast(ET.Element, doc), "input")
            self.assertIsNone(response)
        
        # Test with non-ack response
        xml_data = b'<?xml version="1.0" encoding="utf-8"?><emotivaError>Error message</emotivaError>'
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_command_response(cast(ET.Element, doc), "volume")
            self.assertIsNone(response)
    
    def test_parse_notify_response(self):
        """Test parsing notification responses."""
        # Test v3+ style notify response
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaNotify sequence="123">
                <property name="volume" value="75" zone="1"/>
                <property name="mute" value="no" zone="1"/>
            </emotivaNotify>'''
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_notify_response(cast(ET.Element, doc))
            self.assertIsNotNone(response)
            if response is not None:
                self.assertEqual(response.sequence, 123)
                self.assertEqual(len(response.properties), 2)
                self.assertEqual(response.properties["volume"]["value"], "75")
                self.assertEqual(response.properties["mute"]["value"], "no")
        
        # Test pre-v3 style notify response
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaNotify>
                <volume value="75" zone="1"/>
                <mute value="no" zone="1"/>
            </emotivaNotify>'''
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_notify_response(cast(ET.Element, doc))
            self.assertIsNotNone(response)
            if response is not None:
                self.assertEqual(len(response.properties), 2)
                self.assertEqual(response.properties["volume"]["value"], "75")
                self.assertEqual(response.properties["mute"]["value"], "no")
    
    def test_parse_transponder_response(self):
        """Test parsing transponder responses."""
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaTransponder>
                <model>XMC-2</model>
                <n>Living Room</n>
                <revision>1.0</revision>
                <control>
                    <version>3.1</version>
                    <controlPort>7002</controlPort>
                    <notifyPort>7003</notifyPort>
                    <infoPort>7004</infoPort>
                    <setupPortTCP>7100</setupPortTCP>
                    <keepAlive>30000</keepAlive>
                </control>
            </emotivaTransponder>'''
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_transponder_response(cast(ET.Element, doc))
            self.assertIsNotNone(response)
            if response is not None:
                self.assertEqual(response.model, "XMC-2")
                self.assertEqual(response.name, "Living Room")
                self.assertEqual(response.revision, "1.0")
                self.assertEqual(response.version, "3.1")
                self.assertEqual(response.ports["controlPort"], 7002)
                self.assertEqual(response.ports["notifyPort"], 7003)
                self.assertEqual(response.keepalive_interval, 30000)
    
    def test_parse_bar_notify_response(self):
        """Test parsing bar notification responses."""
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaBarNotify sequence="123">
                <bar id="1" type="volume" value="75" max="100"/>
                <bar id="2" type="balance" value="0" min="-10" max="10"/>
            </emotivaBarNotify>'''
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_bar_notify_response(cast(ET.Element, doc))
            self.assertIsNotNone(response)
            if response is not None:
                self.assertEqual(response.sequence, 123)
                self.assertEqual(len(response.bars), 2)
                self.assertEqual(response.bars[0]["id"], "1")
                self.assertEqual(response.bars[0]["type"], "volume")
                self.assertEqual(response.bars[0]["value"], "75")
                self.assertEqual(response.bars[1]["type"], "balance")
    
    def test_parse_menu_notify_response(self):
        """Test parsing menu notification responses."""
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaMenuNotify sequence="123">
                <row number="1">
                    <col text="Volume" align="left"/>
                    <col text="75" align="right"/>
                </row>
                <row number="2">
                    <col text="Input" align="left"/>
                    <col text="HDMI 1" align="right"/>
                </row>
            </emotivaMenuNotify>'''
        doc = ResponseParser.parse_response(xml_data)
        self.assertIsNotNone(doc)
        if doc is not None:
            response = ResponseParser.parse_menu_notify_response(cast(ET.Element, doc))
            self.assertIsNotNone(response)
            if response is not None:
                self.assertEqual(response.sequence, 123)
                self.assertEqual(len(response.rows), 2)
                self.assertEqual(response.rows[0]["number"], "1")
                self.assertEqual(len(response.rows[0]["columns"]), 2)
                self.assertEqual(response.rows[0]["columns"][0]["text"], "Volume")
                self.assertEqual(response.rows[1]["columns"][1]["text"], "HDMI 1")
    
    def test_parse_any_response(self):
        """Test parsing any type of response."""
        # Test command response
        xml_data = b'<?xml version="1.0" encoding="utf-8"?><emotivaAck><volume status="ack"/></emotivaAck>'
        resp_type, response = ResponseParser.parse_any_response(xml_data)
        self.assertEqual(resp_type, "command")
        self.assertIsNotNone(response)
        
        # Test notification response
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaNotify sequence="123">
                <property name="volume" value="75" zone="1"/>
            </emotivaNotify>'''
        resp_type, response = ResponseParser.parse_any_response(xml_data)
        self.assertEqual(resp_type, "notify")
        self.assertIsNotNone(response)
        
        # Test bar notification
        xml_data = b'''<?xml version="1.0" encoding="utf-8"?>
            <emotivaBarNotify sequence="123">
                <bar id="1" type="volume" value="75" max="100"/>
            </emotivaBarNotify>'''
        resp_type, response = ResponseParser.parse_any_response(xml_data)
        self.assertEqual(resp_type, "bar")
        self.assertIsNotNone(response)
        
        # Test invalid XML
        xml_data = b'<invalid XML>'
        resp_type, response = ResponseParser.parse_any_response(xml_data)
        self.assertEqual(resp_type, "error")
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main() 