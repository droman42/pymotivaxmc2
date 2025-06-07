"""Test cases for pymotivaxmc2.controller module."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any

from pymotivaxmc2.controller import EmotivaController
from pymotivaxmc2.enums import Command, Property, Input, Zone
from pymotivaxmc2.exceptions import EmotivaError, AckTimeoutError


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
    """Integration tests for EmotivaController."""

    @pytest.mark.asyncio
    async def test_full_connection_cycle(self):
        """Test complete connection and disconnection cycle."""
        controller = EmotivaController("192.168.1.100")
        
        mock_discovery_info = {
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
            mock_discovery.fetch_transponder.return_value = mock_discovery_info
            mock_discovery_cls.return_value = mock_discovery
            
            mock_socket_mgr = AsyncMock()
            mock_socket_mgr_cls.return_value = mock_socket_mgr
            
            mock_protocol = AsyncMock()
            mock_protocol_cls.return_value = mock_protocol
            
            mock_dispatcher = AsyncMock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            
            # Connect and use controller
            await controller.connect()
            await controller.power_on()
            await controller.set_volume(-20.0)
            await controller.disconnect()
            
            # Verify operations
            mock_protocol.send_command.assert_has_calls([
                call(Command.POWER_ON.value),
                call(Command.SET_VOLUME.value, {"value": -20.0})
            ])

    def test_controller_error_handling(self):
        """Test controller error handling."""
        controller = EmotivaController("192.168.1.100")
        
        # Test that methods require connection
        with pytest.raises(AttributeError):
            # Should fail because _protocol is None
            asyncio.run(controller.power_on()) 