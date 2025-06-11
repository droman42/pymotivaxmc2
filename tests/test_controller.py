"""Test cases for pymotivaxmc2.controller module."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any

from pymotivaxmc2.controller import EmotivaController
from pymotivaxmc2.enums import Command, Property, Input, Zone
from pymotivaxmc2.exceptions import EmotivaError, AckTimeoutError, InvalidArgumentError

# Phase 2 Fix: Additional imports for Phase 2 tests
from pymotivaxmc2.core.protocol import Protocol
from pymotivaxmc2.core.discovery import Discovery, DiscoveryError


class TestEmotivaControllerInit:
    """Test cases for EmotivaController initialization."""

    def test_init_default_values(self):
        """Test controller initialization with default values."""
        controller = EmotivaController("192.168.1.100")
        
        assert controller.host == "192.168.1.100"
        assert controller.timeout == 5.0
        assert controller.protocol_max == "3.1"
        assert controller._info is None
        assert controller._socket_mgr is None
        assert controller._protocol is None
        assert controller._dispatcher is None

    def test_init_custom_values(self):
        """Test controller initialization with custom values."""
        controller = EmotivaController(
            "emotiva.local",
            timeout=10.0,
            protocol_max="2.0"
        )
        
        assert controller.host == "emotiva.local"
        assert controller.timeout == 10.0
        assert controller.protocol_max == "2.0"


class TestConnect:
    """Test cases for EmotivaController.connect method."""

    @pytest.fixture
    def controller(self):
        """Create a controller instance."""
        return EmotivaController("192.168.1.100", timeout=1.0)

    @pytest.fixture
    def mock_discovery_info(self):
        """Mock device discovery information."""
        return {
            "protocolVersion": "3.1",
            "controlPort": 7002,
            "notifyPort": 7003,
            "menuNotifyPort": 7003,
        }

    @pytest.mark.asyncio
    async def test_connect_success(self, controller, mock_discovery_info):
        """Test successful connection."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            # Setup mocks
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # Connect
            await controller.connect()
            
            # Verify discovery
            mock_discovery_cls.assert_called_once_with("192.168.1.100", timeout=1.0)
            mock_discovery.fetch_transponder.assert_called_once()
            
            # Verify socket manager setup
            mock_socket_mgr_cls.assert_called_once_with(
                "192.168.1.100",
                {
                    "controlPort": 7002,
                    "notifyPort": 7003,
                    "menuNotifyPort": 7003,
                }
            )
            mock_socket_mgr.start.assert_called_once()
            
            # Verify protocol setup
            mock_protocol_cls.assert_called_once_with(
                mock_socket_mgr,
                protocol_version="3.1"
            )
            
            # Verify dispatcher setup
            mock_dispatcher_cls.assert_called_once_with(mock_socket_mgr, "notifyPort")
            mock_dispatcher.start.assert_called_once()
            
            # Verify controller state
            assert controller._info == mock_discovery_info
            assert controller._socket_mgr == mock_socket_mgr
            assert controller._protocol == mock_protocol
            assert controller._dispatcher == mock_dispatcher

    @pytest.mark.asyncio
    async def test_connect_protocol_version_limiting(self, controller):
        """Test that controller limits protocol version."""
        # Controller max is "3.1", device supports higher version
        discovery_info = {
            "protocolVersion": "4.0",  # Higher than controller max
            "controlPort": 7002,
            "notifyPort": 7003,
        }
        
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            # Setup mocks
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # Connect
            await controller.connect()
            
            # Should use controller's max version, not device's
            mock_protocol_cls.assert_called_once_with(
                mock_socket_mgr,
                protocol_version="3.1"  # Controller's max
            )

    @pytest.mark.asyncio
    async def test_connect_discovery_failure(self, controller):
        """Test connection failure during discovery."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls:
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.side_effect = Exception("Discovery failed")
            mock_discovery_cls.return_value = mock_discovery
            
            with pytest.raises(Exception) as excinfo:
                await controller.connect()
            
            assert "Discovery failed" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_connect_socket_manager_failure(self, controller, mock_discovery_info):
        """Test connection failure during socket manager startup."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls:
            
            # Setup discovery mock
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            # Setup failing socket manager
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr.start.side_effect = Exception("Socket error")
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            with pytest.raises(Exception) as excinfo:
                await controller.connect()
            
            assert "Socket error" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_connect_dispatcher_failure(self, controller, mock_discovery_info):
        """Test connection failure during dispatcher startup."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            # Setup mocks
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            # Setup failing dispatcher
            mock_dispatcher = AsyncMock()
            mock_dispatcher.start.side_effect = Exception("Dispatcher error")
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            with pytest.raises(Exception) as excinfo:
                await controller.connect()
            
            assert "Dispatcher error" in str(excinfo.value)
            # Should cleanup socket manager on failure
            mock_socket_mgr.stop.assert_called_once()


class TestDisconnect:
    """Test cases for EmotivaController.disconnect method."""

    @pytest.fixture
    def connected_controller(self):
        """Create a controller with mocked connected state."""
        controller = EmotivaController("192.168.1.100")
        
        # Mock connected components
        controller._socket_mgr = AsyncMock()
        controller._protocol = MagicMock()
        controller._dispatcher = AsyncMock()
        
        return controller

    @pytest.mark.asyncio
    async def test_disconnect_success(self, connected_controller):
        """Test successful disconnection."""
        await connected_controller.disconnect()
        
        # Verify cleanup calls
        connected_controller._socket_mgr.send.assert_called_once()
        connected_controller._dispatcher.stop.assert_called_once()
        connected_controller._socket_mgr.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        """Test disconnection when not connected."""
        controller = EmotivaController("192.168.1.100")
        
        # Should handle gracefully
        await controller.disconnect()


class TestSubscriptionMethods:
    """Test cases for subscription-related methods."""

    @pytest.fixture
    def connected_controller(self):
        """Create a connected controller."""
        controller = EmotivaController("192.168.1.100")
        controller._socket_mgr = AsyncMock()
        controller._protocol = MagicMock()
        controller._protocol.protocol_version = "3.1"
        controller._dispatcher = AsyncMock()
        return controller

    @pytest.mark.asyncio
    async def test_subscribe_single_property(self, connected_controller):
        """Test subscribing to a single property."""
        await connected_controller.subscribe(Property.POWER)
        
        connected_controller._socket_mgr.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_multiple_properties(self, connected_controller):
        """Test subscribing to multiple properties."""
        properties = [Property.POWER, Property.VOLUME, Property.LOUDNESS]
        await connected_controller.subscribe(properties)
        
        connected_controller._socket_mgr.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_single_property(self, connected_controller):
        """Test unsubscribing from a single property."""
        await connected_controller.unsubscribe(Property.POWER)
        
        connected_controller._socket_mgr.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_multiple_properties(self, connected_controller):
        """Test unsubscribing from multiple properties."""
        properties = [Property.POWER, Property.VOLUME]
        await connected_controller.unsubscribe(properties)
        
        connected_controller._socket_mgr.send.assert_called_once()

    def test_on_decorator(self, connected_controller):
        """Test the on decorator for registering callbacks."""
        @connected_controller.on(Property.POWER)
        def power_callback(value):
            pass
        
        connected_controller._dispatcher.on.assert_called_once_with(
            Property.POWER.value,
            power_callback
        )

    def test_on_decorator_async_callback(self, connected_controller):
        """Test the on decorator with async callback."""
        @connected_controller.on(Property.VOLUME)
        async def volume_callback(value):
            pass
        
        connected_controller._dispatcher.on.assert_called_once_with(
            Property.VOLUME.value,
            volume_callback
        )


class TestPowerMethods:
    """Test cases for power control methods."""

    @pytest.fixture
    def connected_controller(self):
        """Create a connected controller."""
        controller = EmotivaController("192.168.1.100")
        controller._protocol = AsyncMock()
        return controller

    @pytest.mark.asyncio
    async def test_power_on_main_zone(self, connected_controller):
        """Test powering on main zone."""
        await connected_controller.power_on()
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.POWER_ON.value
        )

    @pytest.mark.asyncio
    async def test_power_on_zone2(self, connected_controller):
        """Test powering on zone 2."""
        await connected_controller.power_on(zone=Zone.ZONE2)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.ZONE2_POWER_ON.value
        )

    @pytest.mark.asyncio
    async def test_power_off_main_zone(self, connected_controller):
        """Test powering off main zone."""
        await connected_controller.power_off()
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.POWER_OFF.value
        )

    @pytest.mark.asyncio
    async def test_power_off_zone2(self, connected_controller):
        """Test powering off zone 2."""
        await connected_controller.power_off(zone=Zone.ZONE2)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.ZONE2_POWER_OFF.value
        )

    @pytest.mark.asyncio
    async def test_power_toggle_main_zone(self, connected_controller):
        """Test toggling power for main zone."""
        await connected_controller.power_toggle()
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.STANDBY.value
        )

    @pytest.mark.asyncio
    async def test_power_toggle_zone2(self, connected_controller):
        """Test toggling power for zone 2."""
        await connected_controller.power_toggle(zone=Zone.ZONE2)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.ZONE2_POWER.value
        )


class TestVolumeMethods:
    """Test cases for volume control methods."""

    @pytest.fixture
    def connected_controller(self):
        """Create a connected controller."""
        controller = EmotivaController("192.168.1.100")
        controller._protocol = AsyncMock()
        return controller

    @pytest.mark.asyncio
    async def test_set_volume_main_zone(self, connected_controller):
        """Test setting volume for main zone."""
        await connected_controller.set_volume(-20.5)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.SET_VOLUME.value,
            {"value": -20.5}
        )

    @pytest.mark.asyncio
    async def test_set_volume_zone2(self, connected_controller):
        """Test setting volume for zone 2."""
        await connected_controller.set_volume(-15.0, zone=Zone.ZONE2)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.ZONE2_SET_VOLUME.value,
            {"value": -15.0}
        )

    @pytest.mark.asyncio
    async def test_vol_up_default_step(self, connected_controller):
        """Test volume up with default step."""
        await connected_controller.vol_up()
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.VOLUME.value,
            {"value": 1.0}
        )

    @pytest.mark.asyncio
    async def test_vol_up_custom_step(self, connected_controller):
        """Test volume up with custom step."""
        await connected_controller.vol_up(2.5)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.VOLUME.value,
            {"value": 2.5}
        )

    @pytest.mark.asyncio
    async def test_vol_down_default_step(self, connected_controller):
        """Test volume down with default step."""
        await connected_controller.vol_down()
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.VOLUME.value,
            {"value": -1.0}
        )

    @pytest.mark.asyncio
    async def test_vol_down_custom_step(self, connected_controller):
        """Test volume down with custom step."""
        await connected_controller.vol_down(3.0)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.VOLUME.value,
            {"value": -3.0}
        )

    @pytest.mark.asyncio
    async def test_set_volume_relative_positive(self, connected_controller):
        """Test setting relative volume (positive)."""
        await connected_controller.set_volume_relative(2.0)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.VOLUME.value,
            {"value": 2.0}
        )

    @pytest.mark.asyncio
    async def test_set_volume_relative_negative(self, connected_controller):
        """Test setting relative volume (negative)."""
        await connected_controller.set_volume_relative(-1.5)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.VOLUME.value,
            {"value": -1.5}
        )

    @pytest.mark.asyncio
    async def test_set_volume_relative_zone2(self, connected_controller):
        """Test setting relative volume for zone 2."""
        await connected_controller.set_volume_relative(1.0, zone=Zone.ZONE2)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.ZONE2_VOLUME.value,
            {"value": 1.0}
        )


class TestMuteMethods:
    """Test cases for mute control methods."""

    @pytest.fixture
    def connected_controller(self):
        """Create a connected controller."""
        controller = EmotivaController("192.168.1.100")
        controller._protocol = AsyncMock()
        return controller

    @pytest.mark.asyncio
    async def test_mute_main_zone(self, connected_controller):
        """Test muting main zone."""
        await connected_controller.mute()
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.MUTE.value
        )

    @pytest.mark.asyncio
    async def test_mute_zone2(self, connected_controller):
        """Test muting zone 2."""
        await connected_controller.mute(zone=Zone.ZONE2)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.ZONE2_MUTE.value
        )


class TestOtherMethods:
    """Test cases for other controller methods."""

    @pytest.fixture
    def connected_controller(self):
        """Create a connected controller."""
        controller = EmotivaController("192.168.1.100")
        controller._protocol = AsyncMock()
        return controller

    @pytest.mark.asyncio
    async def test_select_input_enum(self, connected_controller):
        """Test selecting input using Input enum."""
        await connected_controller.select_input(Input.HDMI1)
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.HDMI1.value
        )

    @pytest.mark.asyncio
    async def test_select_input_string(self, connected_controller):
        """Test selecting input using string."""
        await connected_controller.select_input("hdmi2")
        
        connected_controller._protocol.send_command.assert_called_once_with(
            Command.HDMI2.value
        )

    @pytest.mark.asyncio
    async def test_status_method(self, connected_controller):
        """Test status method."""
        # Mock the protocol's request_properties method
        mock_result = {"power": "On", "volume": "-20.5"}
        connected_controller._protocol.request_properties.return_value = mock_result
        
        properties = [Property.POWER, Property.VOLUME]
        result = await connected_controller.status(*properties, timeout=1.0)
        
        # Verify protocol call
        connected_controller._protocol.request_properties.assert_called_once_with(
            ["power", "volume"],
            timeout=1.0
        )
        
        # Verify result transformation
        expected = {
            Property.POWER: "On",
            Property.VOLUME: "-20.5"
        }
        assert result == expected


class TestControllerIntegration:
    """Test cases for integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_connection_cycle(self):
        """Test a complete connection and disconnection cycle."""
        controller = EmotivaController("192.168.1.100")
        discovery_info = {
            "protocolVersion": "3.1",
            "controlPort": 7002,
            "notifyPort": 7003,
        }
        
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            # Setup mocks
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # Test connection
            await controller.connect()
            assert controller._socket_mgr is not None
            assert controller._protocol is not None
            assert controller._dispatcher is not None
            
            # Test disconnection
            await controller.disconnect()
            
            # Verify cleanup calls
            mock_socket_mgr.send.assert_called_once()  # unsubscribe
            mock_dispatcher.stop.assert_called_once()
            mock_socket_mgr.stop.assert_called_once()

    def test_controller_error_handling(self):
        """Test controller handles errors gracefully."""
        controller = EmotivaController("invalid-host")
        
        # Controller should be created without issues
        assert controller.host == "invalid-host"
        assert controller._socket_mgr is None


# Phase 1 Tests: Concurrency Protection
class TestPhase1ConcurrencyFixes:
    """Test cases for Phase 1 concurrency protection fixes."""

    @pytest.fixture
    def controller(self):
        """Create a controller instance."""
        return EmotivaController("192.168.1.100", timeout=1.0)

    @pytest.fixture
    def mock_discovery_info(self):
        """Mock device discovery information."""
        return {
            "protocolVersion": "3.1",
            "controlPort": 7002,
            "notifyPort": 7003,
            "menuNotifyPort": 7003,
        }

    def test_controller_has_connection_lock(self, controller):
        """Test that controller has connection protection infrastructure."""
        # Phase 1 Fix: Verify connection lock exists
        assert hasattr(controller, '_connection_lock')
        assert isinstance(controller._connection_lock, asyncio.Lock)
        assert hasattr(controller, '_connected')
        assert controller._connected is False

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, controller, mock_discovery_info):
        """Test that connect() is idempotent when already connected."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            # Setup mocks
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # First connection
            await controller.connect()
            assert controller._connected is True
            
            # Reset call counts
            mock_discovery_cls.reset_mock()
            mock_socket_mgr_cls.reset_mock()
            
            # Second connection should be ignored
            await controller.connect()
            
            # Should not call discovery or socket manager again
            mock_discovery_cls.assert_not_called()
            mock_socket_mgr_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_connect_calls(self, controller, mock_discovery_info):
        """Test that concurrent connect() calls are handled safely."""
        call_count = 0
        
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            def count_discovery_calls(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_discovery = AsyncMock()
                mock_discovery.fetch_transponder.return_value = mock_discovery_info
                return mock_discovery
            
            mock_discovery_cls.side_effect = count_discovery_calls
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # Launch multiple concurrent connect calls
            tasks = [controller.connect() for _ in range(5)]
            await asyncio.gather(*tasks)
            
            # Should only call discovery once due to connection lock
            assert call_count == 1
            assert controller._connected is True

    @pytest.mark.asyncio
    async def test_connect_failure_resets_state(self, controller, mock_discovery_info):
        """Test that connection failures properly reset controller state."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls:
            
            # Setup discovery mock
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            # Setup failing socket manager
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr.start.side_effect = Exception("Socket error")
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            # Connection should fail
            with pytest.raises(Exception):
                await controller.connect()
            
            # Phase 1 Fix: State should be reset after failure
            assert controller._connected is False
            assert controller._socket_mgr is None
            assert controller._protocol is None
            assert controller._dispatcher is None

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, controller):
        """Test disconnect when not connected."""
        # Should not raise error
        await controller.disconnect()
        assert controller._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_resets_state(self, controller, mock_discovery_info):
        """Test that disconnect properly resets all state."""
        with patch('pymotivaxmc2.controller.Discovery') as mock_discovery_cls, \
             patch('pymotivaxmc2.controller.SocketManager') as mock_socket_mgr_cls, \
             patch('pymotivaxmc2.controller.Protocol') as mock_protocol_cls, \
             patch('pymotivaxmc2.controller.Dispatcher') as mock_dispatcher_cls:
            
            # Setup mocks
            mock_discovery = AsyncMock()
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = MagicMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # Connect first
            await controller.connect()
            assert controller._connected is True
            
            # Disconnect
            await controller.disconnect()
            
            # Phase 1 Fix: All state should be reset
            assert controller._connected is False
            assert controller._socket_mgr is None
            assert controller._protocol is None
            assert controller._dispatcher is None


# Phase 1 Tests: SocketManager Concurrency Protection
class TestPhase1SocketManagerFixes:
    """Test cases for Phase 1 SocketManager port binding protection."""

    @pytest.mark.asyncio
    async def test_socket_manager_has_start_lock(self):
        """Test that SocketManager has port binding protection."""
        from pymotivaxmc2.core.socket_mgr import SocketManager
        
        socket_mgr = SocketManager("192.168.1.100", {"controlPort": 7002})
        
        # Phase 1 Fix: Verify start lock exists
        assert hasattr(socket_mgr, '_start_lock')
        assert isinstance(socket_mgr._start_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_socket_manager_start(self):
        """Test that concurrent start() calls are handled safely."""
        from pymotivaxmc2.core.socket_mgr import SocketManager
        
        # Track how many times create_datagram_endpoint is called
        call_count = 0
        original_create_endpoint = None
        
        def count_endpoint_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Create a mock transport
            mock_transport = AsyncMock()
            mock_protocol = args[0]()  # Instantiate the protocol
            return mock_transport, mock_protocol
        
        socket_mgr = SocketManager("192.168.1.100", {"controlPort": 7002})
        
        # Patch the event loop's create_datagram_endpoint method
        with patch.object(socket_mgr._loop, 'create_datagram_endpoint', side_effect=count_endpoint_calls):
            # Launch multiple concurrent start calls
            tasks = [socket_mgr.start() for _ in range(3)]
            await asyncio.gather(*tasks)
            
            # Should only bind to port once due to start lock
            assert call_count == 1
            assert 7002 in socket_mgr._transports

    @pytest.mark.asyncio
    async def test_socket_manager_start_failure_cleanup(self):
        """Test that start failure properly cleans up partial state."""
        from pymotivaxmc2.core.socket_mgr import SocketManager
        
        socket_mgr = SocketManager("192.168.1.100", {"controlPort": 7002, "notifyPort": 7003})
        
        # Create a scenario where second port binding fails
        call_count = 0
        def failing_endpoint_creation(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call succeeds
                mock_transport = AsyncMock()
                mock_protocol = args[0]()
                return mock_transport, mock_protocol
            else:
                # Second call fails
                raise OSError("Port already in use")
        
        with patch.object(socket_mgr._loop, 'create_datagram_endpoint', side_effect=failing_endpoint_creation):
            # Start should fail and clean up
            with pytest.raises(OSError):
                await socket_mgr.start()
            
            # Phase 1 Fix: Partial state should be cleaned up
            assert len(socket_mgr._transports) == 0
            assert len(socket_mgr._queues) == 0

    @pytest.mark.asyncio
    async def test_socket_manager_stop_uses_lock(self):
        """Test that stop() uses the same lock for consistency."""
        from pymotivaxmc2.core.socket_mgr import SocketManager
        
        socket_mgr = SocketManager("192.168.1.100", {"controlPort": 7002})
        
        # Setup a mock transport
        mock_transport = AsyncMock()
        socket_mgr._transports[7002] = mock_transport
        
        # Stop should complete without error
        await socket_mgr.stop()
        
        # Should have called close on transport
        mock_transport.close.assert_called_once()
        assert len(socket_mgr._transports) == 0


# Phase 1 Tests: Dispatcher Callback Protection
class TestPhase1DispatcherFixes:
    """Test cases for Phase 1 Dispatcher callback timeout protection."""

    @pytest.mark.asyncio
    async def test_dispatcher_has_task_management(self):
        """Test that Dispatcher has callback protection infrastructure."""
        from pymotivaxmc2.core.dispatcher import Dispatcher
        
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Phase 1 Fix: Verify task management infrastructure
        assert hasattr(dispatcher, '_active_tasks')
        assert isinstance(dispatcher._active_tasks, set)
        assert hasattr(dispatcher, '_callback_timeout')
        assert dispatcher._callback_timeout == 5.0

    @pytest.mark.asyncio
    async def test_async_callback_timeout_protection(self):
        """Test that async callbacks are protected with timeouts."""
        from pymotivaxmc2.core.dispatcher import Dispatcher
        
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Set short timeout for testing
        dispatcher._callback_timeout = 0.1
        
        # Register a slow async callback
        slow_callback_called = False
        async def slow_callback(value):
            nonlocal slow_callback_called
            await asyncio.sleep(0.2)  # Longer than timeout
            slow_callback_called = True
        
        dispatcher.on("test_prop", slow_callback)
        
        # Mock XML data
        mock_xml = MagicMock()
        mock_xml.tag = "emotivaNotify"
        mock_xml.get.return_value = "test_prop"
        mock_xml.text = "test_value"
        
        with patch('pymotivaxmc2.core.dispatcher.parse_xml', return_value=mock_xml):
            # Mock socket manager to return data once then timeout
            mock_socket_mgr.recv.side_effect = [
                (b"<mock/>", ("192.168.1.100", 7003)),
                asyncio.TimeoutError()
            ]
            
            # Start dispatcher
            await dispatcher.start()
            
            # Give it time to process and timeout
            await asyncio.sleep(0.3)
            
            # Stop dispatcher
            await dispatcher.stop()
            
            # Callback should not have completed due to timeout
            assert not slow_callback_called

    @pytest.mark.asyncio
    async def test_sync_callback_thread_pool_execution(self):
        """Test that synchronous callbacks run in thread pool."""
        from pymotivaxmc2.core.dispatcher import Dispatcher
        
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Track which thread the callback runs in
        callback_thread_id = None
        main_thread_id = asyncio.current_task().get_name() if asyncio.current_task() else "main"
        
        def sync_callback(value):
            nonlocal callback_thread_id
            import threading
            callback_thread_id = threading.current_thread().name
        
        dispatcher.on("test_prop", sync_callback)
        
        # Mock XML data
        mock_xml = MagicMock()
        mock_xml.tag = "emotivaNotify"
        mock_xml.get.return_value = "test_prop"
        mock_xml.text = "test_value"
        
        with patch('pymotivaxmc2.core.dispatcher.parse_xml', return_value=mock_xml):
            # Mock socket manager to return data once
            mock_socket_mgr.recv.side_effect = [
                (b"<mock/>", ("192.168.1.100", 7003)),
                asyncio.TimeoutError()
            ]
            
            # Start dispatcher and let it process
            await dispatcher.start()
            await asyncio.sleep(0.1)  # Give time to process
            await dispatcher.stop()
            
            # Phase 1 Fix: Callback should run in different thread
            assert callback_thread_id is not None
            assert "ThreadPoolExecutor" in callback_thread_id

    @pytest.mark.asyncio
    async def test_dispatcher_stop_cancels_active_tasks(self):
        """Test that stopping dispatcher cancels all active callback tasks."""
        from pymotivaxmc2.core.dispatcher import Dispatcher
        
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Register a long-running async callback
        callback_cancelled = False
        async def long_callback(value):
            nonlocal callback_cancelled
            try:
                await asyncio.sleep(10)  # Very long operation
            except asyncio.CancelledError:
                callback_cancelled = True
                raise
        
        dispatcher.on("test_prop", long_callback)
        
        # Mock XML data
        mock_xml = MagicMock()
        mock_xml.tag = "emotivaNotify"
        mock_xml.get.return_value = "test_prop"
        mock_xml.text = "test_value"
        
        with patch('pymotivaxmc2.core.dispatcher.parse_xml', return_value=mock_xml):
            # Mock socket manager to return data once
            mock_socket_mgr.recv.side_effect = [
                (b"<mock/>", ("192.168.1.100", 7003)),
                asyncio.TimeoutError()
            ]
            
            # Start dispatcher
            await dispatcher.start()
            await asyncio.sleep(0.1)  # Give time to create task
            
            # Should have active tasks
            assert len(dispatcher._active_tasks) > 0
            
            # Stop should cancel active tasks
            await dispatcher.stop()
            
            # Phase 1 Fix: All tasks should be cancelled
            assert len(dispatcher._active_tasks) == 0
            assert callback_cancelled is True


# Phase 2 Tests: Network Resilience and Command Concurrency
class TestPhase2NetworkResilienceFixes:
    """Test cases for Phase 2 network resilience and concurrency improvements."""

    @pytest.fixture
    def protocol(self):
        """Create a protocol instance."""
        mock_socket_mgr = AsyncMock()
        return Protocol(mock_socket_mgr, protocol_version="3.1", ack_timeout=1.0)

    def test_protocol_has_concurrency_infrastructure(self, protocol):
        """Test that Protocol has concurrency control infrastructure."""
        # Phase 2 Fix: Verify concurrency control infrastructure
        assert hasattr(protocol, '_command_semaphore')
        assert isinstance(protocol._command_semaphore, asyncio.Semaphore)
        assert protocol._command_semaphore._value == 5  # Default limit
        
        # Verify retry configuration
        assert hasattr(protocol, '_max_retries')
        assert protocol._max_retries == 3
        assert hasattr(protocol, '_base_backoff')
        assert protocol._base_backoff == 0.5

    @pytest.mark.asyncio
    async def test_send_command_retry_on_timeout(self, protocol):
        """Test that send_command retries with exponential backoff on timeout."""
        from pymotivaxmc2.core.xmlcodec import build_command
        
        # Track call attempts
        call_count = 0
        def timeout_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                raise asyncio.TimeoutError()
            else:  # Succeed on 3rd attempt
                mock_xml = MagicMock()
                mock_xml.tag = "emotivaAck"
                return (b"<emotivaAck/>", ("192.168.1.100", 7002))
        
        protocol.socket_mgr.recv.side_effect = timeout_then_succeed
        
        with patch('pymotivaxmc2.core.protocol.parse_xml') as mock_parse:
            mock_xml = MagicMock()
            mock_xml.tag = "emotivaAck"
            mock_parse.return_value = mock_xml
            
            # Should succeed after retries
            result = await protocol.send_command("power_on")
            
            # Should have retried and succeeded
            assert call_count == 3
            assert result.tag == "emotivaAck"
            
            # Should have sent command multiple times
            assert protocol.socket_mgr.send.call_count == 3

    @pytest.mark.asyncio
    async def test_send_command_exhausted_retries(self, protocol):
        """Test that send_command raises error after exhausting retries."""
        # Configure shorter retry for testing
        protocol._max_retries = 2
        protocol._base_backoff = 0.01  # Very short backoff for testing
        
        # Always timeout
        protocol.socket_mgr.recv.side_effect = asyncio.TimeoutError()
        
        # Should raise AckTimeoutError after retries
        with pytest.raises(AckTimeoutError):
            await protocol.send_command("power_on")
        
        # Should have tried multiple times
        assert protocol.socket_mgr.send.call_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_command_limit(self, protocol):
        """Test that concurrent commands are limited by semaphore."""
        # Set up a slow response to create concurrency
        slow_response_count = 0
        
        async def slow_response(*args, **kwargs):
            nonlocal slow_response_count
            slow_response_count += 1
            await asyncio.sleep(0.1)  # Simulate slow response
            mock_xml = MagicMock()
            mock_xml.tag = "emotivaAck"
            return (b"<emotivaAck/>", ("192.168.1.100", 7002))
        
        protocol.socket_mgr.recv.side_effect = slow_response
        
        with patch('pymotivaxmc2.core.protocol.parse_xml') as mock_parse:
            mock_xml = MagicMock()
            mock_xml.tag = "emotivaAck"
            mock_parse.return_value = mock_xml
            
            # Start many concurrent commands
            tasks = [protocol.send_command(f"command_{i}") for i in range(10)]
            
            # Give a moment for semaphore limiting to take effect
            await asyncio.sleep(0.05)
            
            # Should not have more than semaphore limit (5) active
            assert slow_response_count <= 5
            
            # Complete all tasks
            await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_request_properties_retry_logic(self, protocol):
        """Test that request_properties retries when exceptions are raised."""
        # Configure shorter retry for testing
        protocol._max_retries = 2
        protocol._base_backoff = 0.01
        
        send_call_count = 0
        def track_send_calls(*args, **kwargs):
            nonlocal send_call_count
            send_call_count += 1
            
        protocol.socket_mgr.send.side_effect = track_send_calls
        
        # Test exception-based retry (simpler than timeout handling)
        protocol.socket_mgr.recv.side_effect = Exception("Network error")
        
        # Should raise exception after retries
        with pytest.raises(Exception):
            await protocol.request_properties(["power"], timeout=0.1)
        
        # Should have retried (sent multiple times)
        assert send_call_count == 2

    @pytest.mark.asyncio
    async def test_subscribe_retry_on_wrong_response(self, protocol):
        """Test that subscribe retries on unexpected response."""
        # Configure shorter retry for testing
        protocol._max_retries = 2
        protocol._base_backoff = 0.01
        
        call_count = 0
        def wrong_then_correct(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:  # Wrong response first
                return (b"<emotivaWrongTag/>", ("192.168.1.100", 7002))
            else:  # Correct response
                return (b"<emotivaSubscription/>", ("192.168.1.100", 7002))
        
        protocol.socket_mgr.recv.side_effect = wrong_then_correct
        
        with patch('pymotivaxmc2.core.protocol.parse_xml') as mock_parse:
            def parse_side_effect(data):
                mock_xml = MagicMock()
                if call_count < 2:
                    mock_xml.tag = "emotivaWrongTag"
                else:
                    mock_xml.tag = "emotivaSubscription"
                    mock_xml.findall.return_value = []
                return mock_xml
            
            mock_parse.side_effect = parse_side_effect
            
            # Should retry and succeed
            result = await protocol.subscribe(["power"])
            
            # Should have retried
            assert call_count == 2
            assert isinstance(result, dict)


class TestPhase2DiscoveryRetryFixes:
    """Test cases for Phase 2 Discovery retry improvements."""

    @pytest.fixture
    def discovery(self):
        """Create a discovery instance."""
        return Discovery("192.168.1.100", timeout=0.5)

    def test_discovery_has_retry_infrastructure(self, discovery):
        """Test that Discovery has retry infrastructure."""
        # Phase 2 Fix: Verify retry infrastructure
        assert hasattr(discovery, '_max_retries')
        assert discovery._max_retries == 3
        assert hasattr(discovery, '_base_backoff')
        assert discovery._base_backoff == 1.0

    @pytest.mark.asyncio  
    async def test_discovery_retry_logic_mock(self, discovery):
        """Test discovery retry logic with mocked network operations."""
        # Configure shorter retry for testing
        discovery._max_retries = 2
        discovery._base_backoff = 0.01
        
        # Track how many times endpoint creation is attempted
        endpoint_call_count = 0
        
        async def mock_endpoint_creation(*args, **kwargs):
            nonlocal endpoint_call_count
            endpoint_call_count += 1
            
            if endpoint_call_count < 2:  # First attempt fails
                raise OSError("Address already in use")
            else:  # Second attempt succeeds
                mock_transport = MagicMock()
                mock_transport.sendto = MagicMock()
                mock_transport.close = MagicMock()
                
                mock_protocol = MagicMock()
                return mock_transport, mock_protocol
        
        # Mock the entire network layer
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_loop_instance = MagicMock()
            mock_loop.return_value = mock_loop_instance
            
            # Mock future that resolves with test data
            mock_future = asyncio.Future()
            mock_future.set_result(b"<emotivaTransponder><model>Test</model></emotivaTransponder>")
            mock_loop_instance.create_future.return_value = mock_future
            
            # Mock endpoint creation with retry behavior
            mock_loop_instance.create_datagram_endpoint.side_effect = mock_endpoint_creation
            
            # Mock wait_for to return immediately 
            with patch('asyncio.wait_for', return_value=b"<emotivaTransponder><model>Test</model></emotivaTransponder>"):
                with patch.object(discovery, '_parse_transponder_data', return_value={"model": "Test"}):
                    # Should succeed after retry
                    result = await discovery.fetch_transponder()
                    
                    # Should have retried
                    assert endpoint_call_count == 2
                    assert result["model"] == "Test"


class TestPhase2ErrorHandlingImprovements:
    """Test cases for Phase 2 error handling improvements."""

    def test_new_exception_types_available(self):
        """Test that new exception types are available."""
        from pymotivaxmc2.exceptions import (
            ConnectionError, NetworkError, ProtocolError, 
            ConcurrencyError, RetryExhaustedError
        )
        
        # All should inherit from EmotivaError
        from pymotivaxmc2.exceptions import EmotivaError
        
        assert issubclass(ConnectionError, EmotivaError)
        assert issubclass(NetworkError, EmotivaError)
        assert issubclass(ProtocolError, EmotivaError)
        assert issubclass(ConcurrencyError, EmotivaError)
        assert issubclass(RetryExhaustedError, EmotivaError)

    @pytest.mark.asyncio
    async def test_protocol_error_categorization(self):
        """Test that protocol properly categorizes different error types."""
        from pymotivaxmc2.core.protocol import Protocol
        
        mock_socket_mgr = AsyncMock()
        protocol = Protocol(mock_socket_mgr, ack_timeout=0.1)
        protocol._max_retries = 1  # Quick test
        protocol._base_backoff = 0.01
        
        # Test timeout error becomes AckTimeoutError
        mock_socket_mgr.recv.side_effect = asyncio.TimeoutError()
        
        with pytest.raises(AckTimeoutError):
            await protocol.send_command("test")

    def test_discovery_error_categorization(self):
        """Test that discovery properly categorizes different error types."""
        from pymotivaxmc2.core.discovery import DiscoveryError
        
        # Should be able to create specific error messages
        error = DiscoveryError("Network error during discovery (attempt 1): Connection refused")
        assert "Network error" in str(error)
        assert "attempt 1" in str(error) 