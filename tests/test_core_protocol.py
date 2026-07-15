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
        mock.drain = MagicMock(return_value=0)  # drain() is sync on the real SocketManager
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
        
        # Verify socket manager calls. The recv timeout is the remaining time to
        # the transaction deadline, so it is ~ack_timeout, not exactly it.
        mock_socket_mgr.send.assert_called_once()
        mock_socket_mgr.recv.assert_called_once()
        args, kwargs = mock_socket_mgr.recv.call_args
        assert args[0] == "controlPort"
        assert kwargs["timeout"] == pytest.approx(1.0, abs=0.05)
        
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
    async def test_send_command_stale_frame_discarded(self, protocol, mock_socket_mgr):
        """A stale control-port frame is discarded and the ack still lands.

        Old behavior converted the stale frame into a failed attempt (a full
        re-send); the serialized transaction now discards it and keeps waiting
        within the same attempt — exactly ONE send on the wire.
        """
        stale_xml = b'<?xml version="1.0"?><emotivaUpdate/>'
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.side_effect = [(stale_xml, None), (ack_xml, None)]

        result = await protocol.send_command("power_on")

        assert result is not None
        assert result.tag == "emotivaAck"
        mock_socket_mgr.send.assert_called_once()  # no retry was triggered
        assert mock_socket_mgr.recv.call_count == 2

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
        mock.drain = MagicMock(return_value=0)  # drain() is sync on the real SocketManager
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
        """An empty property request sends NOTHING — an empty Update packet is
        pure device load for zero information (the device has limited
        processing power; every needless packet counts)."""
        result = await protocol_v2.request_properties([], timeout=1.0)

        assert result == {}
        mock_socket_mgr.send.assert_not_called()

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


class TestRequestPropertiesFull:
    """Test cases for Protocol.request_properties_full (value + visible)."""

    @pytest.fixture
    def mock_socket_mgr(self):
        return AsyncMock()

    @pytest.fixture
    def protocol_v3(self, mock_socket_mgr):
        return Protocol(mock_socket_mgr, protocol_version="3.1")

    @pytest.fixture
    def protocol_v2(self, mock_socket_mgr):
        return Protocol(mock_socket_mgr, protocol_version="2.0")

    @pytest.mark.asyncio
    async def test_full_v3_includes_visible(self, protocol_v3, mock_socket_mgr):
        """v3.0+ Update response carries the visible attribute per property."""
        notify_xml = b'''<?xml version="1.0"?>
        <emotivaUpdate>
            <property name="input_1" value="ZAPPITI" visible="true" status="ack"/>
            <property name="input_8" value="HDMI 8" visible="false" status="ack"/>
        </emotivaUpdate>'''
        mock_socket_mgr.recv.return_value = (notify_xml, None)

        result = await protocol_v3.request_properties_full(
            ["input_1", "input_8"], timeout=1.0
        )

        assert result == {
            "input_1": {"value": "ZAPPITI", "visible": True},
            "input_8": {"value": "HDMI 8", "visible": False},
        }

    @pytest.mark.asyncio
    async def test_full_visible_defaults_true(self, protocol_v3, mock_socket_mgr):
        """Missing visible attribute defaults to True."""
        notify_xml = b'''<?xml version="1.0"?>
        <emotivaUpdate>
            <property name="power" value="On"/>
        </emotivaUpdate>'''
        mock_socket_mgr.recv.return_value = (notify_xml, None)

        result = await protocol_v3.request_properties_full(["power"], timeout=1.0)

        assert result == {"power": {"value": "On", "visible": True}}

    @pytest.mark.asyncio
    async def test_request_properties_wraps_full(self, protocol_v3, mock_socket_mgr):
        """request_properties returns value-only, preserving the old shape."""
        notify_xml = b'''<?xml version="1.0"?>
        <emotivaUpdate>
            <property name="input_1" value="ZAPPITI" visible="false"/>
        </emotivaUpdate>'''
        mock_socket_mgr.recv.return_value = (notify_xml, None)

        result = await protocol_v3.request_properties(["input_1"], timeout=1.0)

        assert result == {"input_1": "ZAPPITI"}


class TestSubscribe:
    """Test cases for Protocol.subscribe method."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        mock.drain = MagicMock(return_value=0)  # drain() is sync on the real SocketManager
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
    async def test_subscribe_stale_frame_discarded(self, protocol_v2, mock_socket_mgr):
        """A stale frame while waiting for the subscription confirmation is
        discarded; the confirmation that follows is consumed normally."""
        stale_xml = b'<?xml version="1.0"?><emotivaAck/>'
        sub_xml = b'<?xml version="1.0"?><emotivaSubscription><power status="ack" value="On"/></emotivaSubscription>'
        mock_socket_mgr.recv.side_effect = [(stale_xml, None), (sub_xml, None)]

        result = await protocol_v2.subscribe(["power"])

        assert "power" in result
        mock_socket_mgr.send.assert_called_once()  # stale frame burned no attempt

    @pytest.mark.asyncio
    async def test_subscribe_empty_list(self, protocol_v2, mock_socket_mgr):
        """Test subscription with empty property list."""
        # Mock empty subscription response
        sub_xml = b'<?xml version="1.0"?><emotivaSubscription/>'
        mock_socket_mgr.recv.return_value = (sub_xml, None)
        
        result = await protocol_v2.subscribe([])
        
        assert result == {}
        mock_socket_mgr.send.assert_called_once()


class TestSubscribeInitialDispatch:
    """Subscribe-time fan-out of initial values through registered callbacks."""

    @pytest.fixture
    def mock_socket_mgr(self):
        return AsyncMock()

    @pytest.fixture
    def protocol_v3(self, mock_socket_mgr):
        return Protocol(mock_socket_mgr, protocol_version="3.1")

    @staticmethod
    def _wire_dispatcher(protocol, mock_socket_mgr):
        """Attach a real Dispatcher to the protocol (no run loop started)."""
        from pymotivaxmc2.core.dispatcher import Dispatcher
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        protocol.dispatcher = dispatcher
        return dispatcher

    @staticmethod
    async def _drain(dispatcher):
        """Await any async callback tasks the dispatcher scheduled."""
        if dispatcher._active_tasks:
            await asyncio.gather(*dispatcher._active_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_callback_registered_before_subscribe_gets_initial_value(
        self, protocol_v3, mock_socket_mgr
    ):
        """An @on(prop) callback fires with the value from the subscribe response."""
        dispatcher = self._wire_dispatcher(protocol_v3, mock_socket_mgr)

        received = []
        async def power_cb(value):
            received.append(value)
        dispatcher.on("power", power_cb)

        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <property name="power" status="ack" value="On" visible="true"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)

        result = await protocol_v3.subscribe(["power"])
        await self._drain(dispatcher)

        # Return value contract unchanged...
        assert result == {"power": {"value": "On", "visible": True}}
        # ...and the callback received the initial value.
        assert received == ["On"]

    @pytest.mark.asyncio
    async def test_return_contract_holds_with_dispatcher(
        self, protocol_v3, mock_socket_mgr
    ):
        """The dict return still contains every acked property with value+visible."""
        self._wire_dispatcher(protocol_v3, mock_socket_mgr)

        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <property name="power" status="ack" value="On" visible="true"/>
            <property name="volume" status="ack" value="-20.5" visible="false"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)

        result = await protocol_v3.subscribe(["power", "volume"])

        assert result == {
            "power": {"value": "On", "visible": True},
            "volume": {"value": "-20.5", "visible": False},
        }

    @pytest.mark.asyncio
    async def test_raising_callback_does_not_break_subscribe_or_other_callbacks(
        self, protocol_v3, mock_socket_mgr
    ):
        """A callback that raises during initial dispatch is contained."""
        dispatcher = self._wire_dispatcher(protocol_v3, mock_socket_mgr)

        def bad_cb(value):
            raise RuntimeError("boom")

        good_received = []
        def good_cb(value):
            good_received.append(value)

        dispatcher.on("power", bad_cb)
        dispatcher.on("volume", good_cb)

        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <property name="power" status="ack" value="On" visible="true"/>
            <property name="volume" status="ack" value="-20.5" visible="true"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)

        # Must not raise despite the bad callback.
        result = await protocol_v3.subscribe(["power", "volume"])
        await self._drain(dispatcher)

        assert result == {
            "power": {"value": "On", "visible": True},
            "volume": {"value": "-20.5", "visible": True},
        }
        # The unrelated good callback still fired.
        assert good_received == ["-20.5"]

    @pytest.mark.asyncio
    async def test_property_without_callback_goes_into_return_only(
        self, protocol_v3, mock_socket_mgr
    ):
        """Subscribing to a property with no listener yields the dict, no error."""
        dispatcher = self._wire_dispatcher(protocol_v3, mock_socket_mgr)
        # A listener exists, but for a different property than the one subscribed.
        seen = []
        dispatcher.on("volume", lambda value: seen.append(value))

        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <property name="power" status="ack" value="On" visible="true"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)

        result = await protocol_v3.subscribe(["power"])
        await self._drain(dispatcher)

        assert result == {"power": {"value": "On", "visible": True}}
        assert seen == []

    @pytest.mark.asyncio
    async def test_no_dispatcher_wired_is_a_noop(self, protocol_v3, mock_socket_mgr):
        """Without a dispatcher the subscribe path is unchanged (backward compat)."""
        assert protocol_v3.dispatcher is None

        sub_xml = b'''<?xml version="1.0"?>
        <emotivaSubscription>
            <property name="power" status="ack" value="On" visible="true"/>
        </emotivaSubscription>'''
        mock_socket_mgr.recv.return_value = (sub_xml, None)

        result = await protocol_v3.subscribe(["power"])

        assert result == {"power": {"value": "On", "visible": True}}


class TestProtocolIntegration:
    """Integration tests for Protocol class."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        mock.drain = MagicMock(return_value=0)  # drain() is sync on the real SocketManager
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

class TestControlPortSerialization:
    """LIB-1 (bridge ledger): one control-port transaction in flight at a time."""

    @pytest.fixture
    def mock_socket_mgr(self):
        """Create a mock socket manager."""
        mock = AsyncMock()
        mock.drain = MagicMock(return_value=0)  # drain() is sync on the real SocketManager
        return mock

    @pytest.fixture
    def protocol(self, mock_socket_mgr):
        return Protocol(mock_socket_mgr, protocol_version="3.1", ack_timeout=1.0)

    @pytest.mark.asyncio
    async def test_concurrent_commands_are_serialized(self, protocol, mock_socket_mgr):
        """Two concurrent send_command calls never interleave on the wire:
        the second send happens only after the first transaction's reply."""
        events: list[str] = []
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'

        async def fake_send(data, port):
            events.append("send")

        async def fake_recv(port, timeout=None):
            events.append("recv")
            await asyncio.sleep(0.01)  # give the other task a chance to interleave
            return (ack_xml, None)

        mock_socket_mgr.send.side_effect = fake_send
        mock_socket_mgr.recv.side_effect = fake_recv

        await asyncio.gather(
            protocol.send_command("power_on"),
            protocol.send_command("power_off"),
        )

        # Serialized: send,recv,send,recv — never send,send,...
        assert events == ["send", "recv", "send", "recv"]

    @pytest.mark.asyncio
    async def test_stale_frames_drained_before_send(self, protocol, mock_socket_mgr):
        """Every transaction drains the control-port queue before sending, so a
        dead transaction's late reply can never be consumed by the next one."""
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (ack_xml, None)

        await protocol.send_command("power_on")

        mock_socket_mgr.drain.assert_called_once_with("controlPort")

    @pytest.mark.asyncio
    async def test_update_transaction_drains_and_serializes(self, protocol, mock_socket_mgr):
        """request_properties_full participates in the same serialization +
        drain discipline as commands."""
        update_xml = (
            b'<?xml version="1.0"?><emotivaUpdate protocol="3.1">'
            b'<property name="power" value="On" visible="true" status="ack"/>'
            b'</emotivaUpdate>'
        )
        mock_socket_mgr.recv.return_value = (update_xml, None)

        result = await protocol.request_properties_full(["power"], timeout=0.5)

        assert result["power"]["value"] == "On"
        mock_socket_mgr.drain.assert_called_with("controlPort")
        assert protocol._control_lock.locked() is False  # released after the transaction


class TestRetryDampingAndPacing:
    """LIB-2 (bridge ledger): per-call retries, ack='no', pacing, missing-only batch retry."""

    @pytest.fixture
    def mock_socket_mgr(self):
        mock = AsyncMock()
        mock.drain = MagicMock(return_value=0)  # drain() is sync on the real SocketManager
        return mock

    @pytest.fixture
    def protocol(self, mock_socket_mgr):
        return Protocol(mock_socket_mgr, protocol_version="3.1", ack_timeout=0.05)

    @pytest.mark.asyncio
    async def test_retries_zero_sends_exactly_once(self, protocol, mock_socket_mgr):
        """retries=0 = one attempt: a readiness-sensitive caller must never
        multiply packets at a busy device."""
        mock_socket_mgr.recv.side_effect = asyncio.TimeoutError()

        with pytest.raises(AckTimeoutError):
            await protocol.send_command("power_on", retries=0)

        mock_socket_mgr.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_negative_rejected(self, protocol):
        with pytest.raises(ValueError):
            await protocol.send_command("power_on", retries=-1)

    @pytest.mark.asyncio
    async def test_ack_no_is_fire_and_forget(self, protocol, mock_socket_mgr):
        """ack=False builds ack='no' (spec: the ack is optional), sends once,
        awaits nothing, returns None."""
        result = await protocol.send_command("power_on", ack=False)

        assert result is None
        mock_socket_mgr.send.assert_called_once()
        sent = mock_socket_mgr.send.call_args[0][0]
        assert b'ack="no"' in sent
        mock_socket_mgr.recv.assert_not_called()

    @pytest.mark.asyncio
    async def test_ack_yes_is_explicit_in_frame(self, protocol, mock_socket_mgr):
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        mock_socket_mgr.recv.return_value = (ack_xml, None)

        await protocol.send_command("power_on")

        sent = mock_socket_mgr.send.call_args[0][0]
        assert b'ack="yes"' in sent

    @pytest.mark.asyncio
    async def test_min_send_interval_paces_sends(self, mock_socket_mgr):
        """Two back-to-back commands are separated by at least the pacing interval."""
        protocol = Protocol(mock_socket_mgr, ack_timeout=0.5, min_send_interval=0.08)
        ack_xml = b'<?xml version="1.0"?><emotivaAck/>'
        send_times: list[float] = []

        async def fake_send(data, port):
            send_times.append(asyncio.get_event_loop().time())

        mock_socket_mgr.send.side_effect = fake_send
        mock_socket_mgr.recv.return_value = (ack_xml, None)

        await protocol.send_command("power_on")
        await protocol.send_command("power_off")

        assert len(send_times) == 2
        assert send_times[1] - send_times[0] >= 0.08

    @pytest.mark.asyncio
    async def test_batch_retry_requests_only_missing(self, mock_socket_mgr):
        """A partial Update response retries ONLY the missing properties —
        never the whole batch."""
        protocol = Protocol(mock_socket_mgr, protocol_version="3.1", ack_timeout=0.5)
        partial = (
            b'<?xml version="1.0"?><emotivaUpdate protocol="3.1">'
            b'<property name="power" value="On" visible="true" status="ack"/>'
            b'</emotivaUpdate>'
        )
        complete = (
            b'<?xml version="1.0"?><emotivaUpdate protocol="3.1">'
            b'<property name="volume" value="-40.0" visible="true" status="ack"/>'
            b'</emotivaUpdate>'
        )
        # attempt 1: partial answer then silence; attempt 2: the missing one
        mock_socket_mgr.recv.side_effect = [
            (partial, None), asyncio.TimeoutError(),
            (complete, None),
        ]

        result = await protocol.request_properties_full(
            ["power", "volume"], timeout=0.1, retries=1
        )

        assert result["power"]["value"] == "On"
        assert result["volume"]["value"] == "-40.0"
        assert mock_socket_mgr.send.call_count == 2
        second_update = mock_socket_mgr.send.call_args_list[1][0][0]
        assert b"volume" in second_update
        assert b"power" not in second_update  # missing-only re-request
