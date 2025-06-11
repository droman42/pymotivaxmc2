"""Test cases for pymotivaxmc2.core.protocol module."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import xml.etree.ElementTree as ET

from pymotivaxmc2.core.protocol import Protocol
from pymotivaxmc2.exceptions import AckTimeoutError


class TestProtocolInit:
    """Test cases for Protocol initialization."""

    def test_init_default_values(self):
        """Test Protocol initialization with default values."""
        mock_socket_mgr = MagicMock()
        protocol = Protocol(mock_socket_mgr)
        
        assert protocol.socket_mgr is mock_socket_mgr
        assert protocol.protocol_version == "2.0"
        assert protocol.ack_timeout == 2.0

    def test_init_custom_values(self):
        """Test Protocol initialization with custom values."""
        mock_socket_mgr = MagicMock()
        protocol = Protocol(
            mock_socket_mgr,
            protocol_version="3.1",
            ack_timeout=5.0
        )
        
        assert protocol.socket_mgr is mock_socket_mgr
        assert protocol.protocol_version == "3.1"
        assert protocol.ack_timeout == 5.0


class TestSendCommand:
    """Test cases for Protocol.send_command method."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def protocol(self, mock_socket_mgr):
        """Create a Protocol instance with mocked socket manager."""
        return Protocol(mock_socket_mgr, ack_timeout=1.0)

    @pytest.mark.asyncio
    async def test_send_command_success(self, protocol, mock_socket_mgr):
        """Test successful command sending with ack."""
        # Mock successful ack response
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (ack_xml, None)
        
        # Send command
        result = await protocol.send_command("power_on")
        
        # Verify socket manager calls
        mock_socket_mgr.send.assert_called_once()
        mock_socket_mgr.recv.assert_called_once_with("controlPort", timeout=1.0)
        
        # Verify result
        assert result is not None
        assert result.tag == "emotivaAck"

    @pytest.mark.asyncio
    async def test_send_command_with_params(self, protocol, mock_socket_mgr):
        """Test sending command with parameters."""
        # Mock successful ack response
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (ack_xml, None)
        
        params = {"value": "-20.5", "zone": "main"}
        await protocol.send_command("set_volume", params)
        
        # Verify send was called (content verified in xmlcodec tests)
        mock_socket_mgr.send.assert_called_once()
        call_args = mock_socket_mgr.send.call_args
        sent_data = call_args[0][0]
        sent_port = call_args[0][1]
        
        assert sent_port == "controlPort"
        assert isinstance(sent_data, bytes)

    @pytest.mark.asyncio
    async def test_send_command_ack_timeout(self, protocol, mock_socket_mgr):
        """Test command sending with ack timeout."""
        # Mock timeout
        mock_socket_mgr.recv.side_effect = asyncio.TimeoutError()
        
        with pytest.raises(AckTimeoutError) as excinfo:
            await protocol.send_command("power_on")
        
        assert "No ack received for command 'power_on'" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_send_command_wrong_response_tag(self, protocol, mock_socket_mgr):
        """Test command sending with wrong response tag."""
        # Mock wrong response
        wrong_xml = b'<?xml version="1.0"?><emotivaNotify/>'
        mock_socket_mgr.recv.return_value = (wrong_xml, None)
        
        with pytest.raises(AckTimeoutError) as excinfo:
            await protocol.send_command("power_on")
        
        assert "Unexpected response: emotivaNotify" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_send_command_no_params(self, protocol, mock_socket_mgr):
        """Test sending command with None params."""
        # Mock successful ack response
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (ack_xml, None)
        
        await protocol.send_command("power_on", None)
        
        # Should not raise error
        mock_socket_mgr.send.assert_called_once()


class TestRequestProperties:
    """Test cases for Protocol.request_properties method."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def protocol_v2(self, mock_socket_mgr):
        """Create a Protocol v2.0 instance."""
        return Protocol(mock_socket_mgr, protocol_version="2.0")

    @pytest.fixture
    def protocol_v3(self, mock_socket_mgr):
        """Create a Protocol v3.1 instance."""
        return Protocol(mock_socket_mgr, protocol_version="3.1")

    @pytest.mark.asyncio
    async def test_request_properties_v2_success(self, protocol_v2, mock_socket_mgr):
        """Test successful property request with protocol v2.0."""
        # Mock property responses (v2.0 format)
        notify_xml = b'''<?xml version="1.0"?>
        <emotivaNotify>
            <power>On</power>
            <volume value="-20.5">-20.5</volume>
        </emotivaNotify>'''
        mock_socket_mgr.recv.return_value = (notify_xml, None)
        
        properties = ["power", "volume"]
        result = await protocol_v2.request_properties(properties, timeout=1.0)
        
        assert result == {"power": "On", "volume": "-20.5"}
        mock_socket_mgr.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_properties_v3_success(self, protocol_v3, mock_socket_mgr):
        """Test successful property request with protocol v3.0+."""
        # Mock property responses (v3.0+ format)
        notify_xml = b'''<?xml version="1.0"?>
        <emotivaNotify>
            <property name="power" value="On"/>
            <property name="volume" value="-20.5"/>
        </emotivaNotify>'''
        mock_socket_mgr.recv.return_value = (notify_xml, None)
        
        properties = ["power", "volume"]
        result = await protocol_v3.request_properties(properties, timeout=1.0)
        
        assert result == {"power": "On", "volume": "-20.5"}

    @pytest.mark.asyncio
    async def test_request_properties_timeout(self, protocol_v2, mock_socket_mgr):
        """Test property request with timeout."""
        # Mock timeout on first recv
        mock_socket_mgr.recv.side_effect = asyncio.TimeoutError()
        
        properties = ["power"]
        result = await protocol_v2.request_properties(properties, timeout=0.1)
        
        # Should return partial results (empty in this case)
        assert result == {}

    @pytest.mark.asyncio
    async def test_request_properties_partial_response(self, protocol_v2, mock_socket_mgr):
        """Test property request with partial response."""
        # Mock partial response - only one of two requested properties
        notify_xml = b'''<?xml version="1.0"?>
        <emotivaNotify>
            <power>On</power>
        </emotivaNotify>'''
        
        # Phase 2 Fix: With retry logic, each retry sends a new request
        # For this test, let's just have the final attempt succeed with partial data
        # to avoid complex timeout orchestration
        mock_socket_mgr.recv.side_effect = [
            (notify_xml, None),          # First response with partial data
            asyncio.TimeoutError(),      # Timeout waiting for more properties (attempt 1)
            (notify_xml, None),          # Retry 1: same partial response  
            asyncio.TimeoutError(),      # Timeout waiting for more properties (retry 1)
            (notify_xml, None),          # Retry 2: same partial response
            asyncio.TimeoutError(),      # Timeout waiting for more properties (retry 2)
        ]
        
        properties = ["power", "volume"]
        result = await protocol_v2.request_properties(properties, timeout=0.1)
        
        # Should return partial data after all retries
        assert result == {"power": "On"}
        # Should have made multiple recv calls due to retries
        assert mock_socket_mgr.recv.call_count >= 2

    @pytest.mark.asyncio
    async def test_request_properties_empty_list(self, protocol_v2, mock_socket_mgr):
        """Test property request with empty property list."""
        result = await protocol_v2.request_properties([], timeout=1.0)
        
        assert result == {}
        # Should still send the request
        mock_socket_mgr.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_properties_unexpected_tag(self, protocol_v2, mock_socket_mgr):
        """Test property request with unexpected XML tag."""
        # Mock unexpected response
        unexpected_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (unexpected_xml, None)
        
        properties = ["power"]
        result = await protocol_v2.request_properties(properties, timeout=1.0)
        
        # Should handle gracefully and continue waiting for more
        assert isinstance(result, dict)


class TestSubscribe:
    """Test cases for Protocol.subscribe method."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def protocol_v2(self, mock_socket_mgr):
        """Create a Protocol v2.0 instance."""
        return Protocol(mock_socket_mgr, protocol_version="2.0")

    @pytest.fixture
    def protocol_v3(self, mock_socket_mgr):
        """Create a Protocol v3.1 instance."""
        return Protocol(mock_socket_mgr, protocol_version="3.1")

    @pytest.mark.asyncio
    async def test_subscribe_v2_success(self, protocol_v2, mock_socket_mgr):
        """Test successful subscription with protocol v2.0."""
        # Mock subscription confirmation (v2.0 format)
        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <power status="ack" value="On" visible="true"/>
            <volume status="ack" value="-20.5" visible="true"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)
        
        properties = ["power", "volume"]
        result = await protocol_v2.subscribe(properties)
        
        expected = {
            "power": {"value": "On", "visible": True},
            "volume": {"value": "-20.5", "visible": True}
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_subscribe_v3_success(self, protocol_v3, mock_socket_mgr):
        """Test successful subscription with protocol v3.0+."""
        # Mock subscription confirmation (v3.0+ format)
        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <property name="power" status="ack" value="On" visible="true"/>
            <property name="volume" status="ack" value="-20.5" visible="false"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)
        
        properties = ["power", "volume"]
        result = await protocol_v3.subscribe(properties)
        
        expected = {
            "power": {"value": "On", "visible": True},
            "volume": {"value": "-20.5", "visible": False}
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_subscribe_failed_property(self, protocol_v2, mock_socket_mgr):
        """Test subscription with failed property."""
        # Mock subscription with one failed property
        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <power status="ack" value="On" visible="true"/>
            <invalid_prop status="fail"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)
        
        properties = ["power", "invalid_prop"]
        result = await protocol_v2.subscribe(properties)
        
        # Should only include successful subscriptions
        assert result == {"power": {"value": "On", "visible": True}}

    @pytest.mark.asyncio
    async def test_subscribe_timeout(self, protocol_v2, mock_socket_mgr):
        """Test subscription timeout."""
        mock_socket_mgr.recv.side_effect = asyncio.TimeoutError()
        
        with pytest.raises(AckTimeoutError) as excinfo:
            await protocol_v2.subscribe(["power"])
        
        assert "No subscription confirmation received" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_subscribe_unexpected_response(self, protocol_v2, mock_socket_mgr):
        """Test subscription with unexpected response."""
        # Mock wrong response type
        wrong_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (wrong_xml, None)
        
        result = await protocol_v2.subscribe(["power"])
        
        # Should return empty dict for unexpected response
        assert result == {}

    @pytest.mark.asyncio
    async def test_subscribe_empty_list(self, protocol_v2, mock_socket_mgr):
        """Test subscription with empty property list."""
        # Mock empty subscription response
        sub_xml = b'<?xml version="1.0"?><emotivaSubscription/>'
        mock_socket_mgr.recv.return_value = (sub_xml, None)
        
        result = await protocol_v2.subscribe([])
        
        assert result == {}
        mock_socket_mgr.send.assert_called_once()


class TestProtocolIntegration:
    """Integration tests for Protocol class."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_protocol_version_affects_xml_generation(self, mock_socket_mgr):
        """Test that protocol version affects XML generation."""
        protocol_v2 = Protocol(mock_socket_mgr, protocol_version="2.0")
        protocol_v3 = Protocol(mock_socket_mgr, protocol_version="3.1")
        
        # Mock responses
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (ack_xml, None)
        
        # Send commands with both protocols
        await protocol_v2.send_command("power_on")
        await protocol_v3.send_command("power_on")
        
        # Both should work (XML differences are in build functions, tested separately)
        assert mock_socket_mgr.send.call_count == 2

    @pytest.mark.asyncio
    async def test_ack_timeout_configuration(self, mock_socket_mgr):
        """Test that ack timeout is configurable."""
        protocol = Protocol(mock_socket_mgr, ack_timeout=0.05)  # Very short timeout
        
        # Mock timeout exception directly
        mock_socket_mgr.recv.side_effect = asyncio.TimeoutError("Test timeout")
        
        # Should timeout quickly
        with pytest.raises(AckTimeoutError):
            await protocol.send_command("power_on")

    @pytest.mark.asyncio
    async def test_protocol_error_handling(self, mock_socket_mgr):
        """Test protocol error handling."""
        protocol = Protocol(mock_socket_mgr)
        
        # Test exception propagation from socket manager
        mock_socket_mgr.send.side_effect = Exception("Network error")
        
        with pytest.raises(Exception) as excinfo:
            await protocol.send_command("power_on")
        
        assert "Network error" in str(excinfo.value) 