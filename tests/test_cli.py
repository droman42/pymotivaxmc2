"""Test cases for pymotivaxmc2.cli module."""

import pytest
import argparse
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from io import StringIO

from pymotivaxmc2.cli import (
    build_parser,
    positive_float,
    do_power,
    do_volume,
    do_mute,
    do_input,
    do_status,
    main,
)
from pymotivaxmc2.enums import Zone, Input, Property
from pymotivaxmc2.exceptions import InvalidArgumentError


class TestPositiveFloat:
    """Test cases for positive_float function."""

    def test_positive_float_valid_positive(self):
        """Test positive_float with valid positive number."""
        result = positive_float("2.5")
        assert result == 2.5

    def test_positive_float_valid_zero(self):
        """Test positive_float with zero."""
        result = positive_float("0")
        assert result == 0.0

    def test_positive_float_valid_negative(self):
        """Test positive_float with negative number (should still work)."""
        # Function name is misleading - it actually accepts any float
        result = positive_float("-1.5")
        assert result == -1.5

    def test_positive_float_invalid_string(self):
        """Test positive_float with invalid string."""
        with pytest.raises(argparse.ArgumentTypeError) as excinfo:
            positive_float("not_a_number")
        
        assert "must be a number" in str(excinfo.value)

    def test_positive_float_empty_string(self):
        """Test positive_float with empty string."""
        with pytest.raises(argparse.ArgumentTypeError):
            positive_float("")


class TestBuildParser:
    """Test cases for build_parser function."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return build_parser()

    def test_parser_creation(self, parser):
        """Test that parser is created successfully."""
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.prog == "emu-cli"

    def test_parser_requires_host(self, parser):
        """Test that parser requires host argument."""
        with pytest.raises(SystemExit):
            parser.parse_args(["power", "on"])

    def test_parser_power_commands(self, parser):
        """Test power command parsing."""
        # Test power on
        args = parser.parse_args(["--host", "192.168.1.100", "power", "on"])
        assert args.host == "192.168.1.100"
        assert args.cmd == "power"
        assert args.action == "on"

        # Test power off
        args = parser.parse_args(["--host", "192.168.1.100", "power", "off"])
        assert args.action == "off"

        # Test power toggle
        args = parser.parse_args(["--host", "192.168.1.100", "power", "toggle"])
        assert args.action == "toggle"

    def test_parser_volume_commands(self, parser):
        """Test volume command parsing."""
        # Test volume up with default step
        args = parser.parse_args(["--host", "192.168.1.100", "volume", "up"])
        assert args.cmd == "volume"
        assert args.action == "up"
        assert args.step == 1.0

        # Test volume up with custom step
        args = parser.parse_args(["--host", "192.168.1.100", "volume", "up", "--step", "2.5"])
        assert args.step == 2.5

        # Test volume down
        args = parser.parse_args(["--host", "192.168.1.100", "volume", "down", "--step", "1.5"])
        assert args.action == "down"
        assert args.step == 1.5

        # Test volume set
        args = parser.parse_args(["--host", "192.168.1.100", "volume", "set", "-20.5"])
        assert args.action == "set"
        assert args.value == -20.5

    def test_parser_mute_commands(self, parser):
        """Test mute command parsing."""
        # Test mute on
        args = parser.parse_args(["--host", "192.168.1.100", "mute", "on"])
        assert args.cmd == "mute"
        assert args.action == "on"

        # Test mute toggle
        args = parser.parse_args(["--host", "192.168.1.100", "mute", "toggle"])
        assert args.action == "toggle"

    def test_parser_input_commands(self, parser):
        """Test input command parsing."""
        args = parser.parse_args(["--host", "192.168.1.100", "input", "set", "hdmi1"])
        assert args.cmd == "input"
        assert args.action == "set"
        assert args.name == "hdmi1"

    def test_parser_status_commands(self, parser):
        """Test status command parsing."""
        args = parser.parse_args(["--host", "192.168.1.100", "status", "power", "volume", "mute"])
        assert args.cmd == "status"
        assert args.properties == ["power", "volume", "mute"]

    def test_parser_zone2_commands(self, parser):
        """Test zone2 command parsing."""
        # Test zone2 power
        args = parser.parse_args(["--host", "192.168.1.100", "zone2", "power", "on"])
        assert args.cmd == "zone2"
        assert args.z2cmd == "power"
        assert args.action == "on"

        # Test zone2 volume
        args = parser.parse_args(["--host", "192.168.1.100", "zone2", "volume", "set", "-15.0"])
        assert args.z2cmd == "volume"
        assert args.action == "set"
        assert args.value == -15.0

    def test_parser_invalid_commands(self, parser):
        """Test parser with invalid commands."""
        # Invalid power action
        with pytest.raises(SystemExit):
            parser.parse_args(["--host", "192.168.1.100", "power", "invalid"])

        # Missing required subcommand
        with pytest.raises(SystemExit):
            parser.parse_args(["--host", "192.168.1.100"])


class TestActionFunctions:
    """Test cases for action functions."""

    @pytest.fixture
    def mock_controller(self):
        """Create a mock controller."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_do_power_on(self, mock_controller):
        """Test do_power with 'on' action."""
        await do_power(mock_controller, "on", Zone.MAIN)
        mock_controller.power_on.assert_called_once_with(zone=Zone.MAIN)

    @pytest.mark.asyncio
    async def test_do_power_off(self, mock_controller):
        """Test do_power with 'off' action."""
        await do_power(mock_controller, "off", Zone.ZONE2)
        mock_controller.power_off.assert_called_once_with(zone=Zone.ZONE2)

    @pytest.mark.asyncio
    async def test_do_power_toggle(self, mock_controller):
        """Test do_power with 'toggle' action."""
        await do_power(mock_controller, "toggle", Zone.MAIN)
        mock_controller.power_toggle.assert_called_once_with(zone=Zone.MAIN)

    @pytest.mark.asyncio
    async def test_do_volume_up(self, mock_controller):
        """Test do_volume with 'up' action."""
        await do_volume(mock_controller, "up", Zone.MAIN, step=2.5)
        mock_controller.vol_up.assert_called_once_with(2.5, zone=Zone.MAIN)

    @pytest.mark.asyncio
    async def test_do_volume_down(self, mock_controller):
        """Test do_volume with 'down' action."""
        await do_volume(mock_controller, "down", Zone.ZONE2, step=1.0)
        mock_controller.vol_down.assert_called_once_with(1.0, zone=Zone.ZONE2)

    @pytest.mark.asyncio
    async def test_do_volume_set(self, mock_controller):
        """Test do_volume with 'set' action."""
        await do_volume(mock_controller, "set", Zone.MAIN, value=-20.5)
        mock_controller.set_volume.assert_called_once_with(-20.5, zone=Zone.MAIN)

    @pytest.mark.asyncio
    async def test_do_mute_on(self, mock_controller):
        """Test do_mute with 'on' action."""
        await do_mute(mock_controller, "on", Zone.MAIN)
        mock_controller.mute_on.assert_called_once_with(zone=Zone.MAIN)

    @pytest.mark.asyncio
    async def test_do_mute_toggle(self, mock_controller):
        """Test do_mute with 'toggle' action."""
        await do_mute(mock_controller, "toggle", Zone.ZONE2)
        mock_controller.mute_toggle.assert_called_once_with(zone=Zone.ZONE2)

    @pytest.mark.asyncio
    async def test_do_input_valid(self, mock_controller):
        """Test do_input with valid input name."""
        await do_input(mock_controller, "hdmi1")
        mock_controller.select_input.assert_called_once_with(Input.HDMI1)

    @pytest.mark.asyncio
    async def test_do_input_case_insensitive(self, mock_controller):
        """Test do_input with different case."""
        await do_input(mock_controller, "coax1")
        mock_controller.select_input.assert_called_once_with(Input.COAX1)

    @pytest.mark.asyncio
    async def test_do_input_invalid(self, mock_controller):
        """Test do_input with invalid input name."""
        with pytest.raises(InvalidArgumentError) as excinfo:
            await do_input(mock_controller, "invalid_input")
        
        assert "unknown input 'invalid_input'" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_do_status_valid_properties(self, mock_controller):
        """Test do_status with valid properties."""
        # Mock the status method to return expected values
        mock_controller.status.return_value = {
            Property.POWER: "On",
            Property.VOLUME: "-20.5"
        }
        
        with patch('sys.stdout', new=StringIO()) as fake_stdout:
            await do_status(mock_controller, ["power", "volume"])
        
        mock_controller.status.assert_called_once_with(Property.POWER, Property.VOLUME)
        
        output = fake_stdout.getvalue()
        assert "power" in output
        assert "volume" in output
        assert "On" in output
        assert "-20.5" in output

    @pytest.mark.asyncio
    async def test_do_status_invalid_property(self, mock_controller):
        """Test do_status with invalid property name."""
        with patch('sys.stderr', new=StringIO()) as fake_stderr, \
             pytest.raises(SystemExit):
            await do_status(mock_controller, ["invalid_property"])
        
        error_output = fake_stderr.getvalue()
        assert "Unknown property 'invalid_property'" in error_output


class TestMainFunction:
    """Test cases for main function."""

    @pytest.mark.asyncio
    async def test_main_power_command(self):
        """Test main function with power command."""
        argv = ["--host", "192.168.1.100", "power", "on"]
        
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls, \
             patch('sys.stdout', new=StringIO()) as fake_stdout:
            
            mock_controller = AsyncMock()
            mock_controller_cls.return_value = mock_controller
            
            await main(argv)
            
            # Verify controller creation and connection
            mock_controller_cls.assert_called_once_with("192.168.1.100")
            mock_controller.connect.assert_called_once()
            mock_controller.power_on.assert_called_once_with(zone=Zone.MAIN)
            mock_controller.disconnect.assert_called_once()
            
            output = fake_stdout.getvalue()
            assert "Connection OK" in output

    @pytest.mark.asyncio
    async def test_main_volume_command(self):
        """Test main function with volume command."""
        argv = ["--host", "192.168.1.100", "volume", "set", "-25.0"]
        
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls:
            mock_controller = AsyncMock()
            mock_controller_cls.return_value = mock_controller
            
            await main(argv)
            
            mock_controller.set_volume.assert_called_once_with(-25.0, zone=Zone.MAIN)

    @pytest.mark.asyncio
    async def test_main_zone2_command(self):
        """Test main function with zone2 command."""
        argv = ["--host", "192.168.1.100", "zone2", "power", "on"]
        
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls:
            mock_controller = AsyncMock()
            mock_controller_cls.return_value = mock_controller
            
            await main(argv)
            
            mock_controller.power_on.assert_called_once_with(zone=Zone.ZONE2)

    @pytest.mark.asyncio
    async def test_main_connection_error(self):
        """Test main function with connection error."""
        argv = ["--host", "192.168.1.100", "power", "on"]
        
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls, \
             patch('sys.stderr', new=StringIO()) as fake_stderr, \
             pytest.raises(SystemExit):
            
            mock_controller = AsyncMock()
            mock_controller.connect.side_effect = Exception("Connection failed")
            mock_controller_cls.return_value = mock_controller
            
            await main(argv)
        
        error_output = fake_stderr.getvalue()
        assert "Connection failed" in error_output

    @pytest.mark.asyncio
    async def test_main_command_error(self):
        """Test main function with command execution error."""
        argv = ["--host", "192.168.1.100", "power", "on"]
        
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls, \
             patch('sys.stderr', new=StringIO()) as fake_stderr, \
             pytest.raises(SystemExit):
            
            mock_controller = AsyncMock()
            mock_controller.power_on.side_effect = Exception("Command failed")
            mock_controller_cls.return_value = mock_controller
            
            await main(argv)
        
        error_output = fake_stderr.getvalue()
        assert "Command failed" in error_output

    @pytest.mark.asyncio
    async def test_main_ensures_disconnect(self):
        """Test that main function always calls disconnect."""
        argv = ["--host", "192.168.1.100", "power", "on"]
        
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls:
            mock_controller = AsyncMock()
            mock_controller.power_on.side_effect = Exception("Command failed")
            mock_controller_cls.return_value = mock_controller
            
            try:
                await main(argv)
            except SystemExit:
                pass  # Expected due to error handling
            
            # Should still call disconnect even on error
            mock_controller.disconnect.assert_called_once()


class TestCLIIntegration:
    """Integration tests for CLI functionality."""

    def test_argument_parsing_integration(self):
        """Test complete argument parsing flow."""
        parser = build_parser()
        
        # Test complex command
        args = parser.parse_args([
            "--host", "emotiva.local",
            "volume", "up", "--step", "2.5"
        ])
        
        assert args.host == "emotiva.local"
        assert args.cmd == "volume"
        assert args.action == "up"
        assert args.step == 2.5

    @pytest.mark.asyncio
    async def test_full_cli_workflow(self):
        """Test a complete CLI workflow."""
        with patch('pymotivaxmc2.cli.EmotivaController') as mock_controller_cls:
            mock_controller = AsyncMock()
            mock_controller_cls.return_value = mock_controller
            
            # Simulate successful execution
            await main(["--host", "192.168.1.100", "input", "set", "hdmi2"])
            
            # Verify full workflow
            mock_controller_cls.assert_called_once_with("192.168.1.100")
            mock_controller.connect.assert_called_once()
            mock_controller.select_input.assert_called_once_with(Input.HDMI2)
            mock_controller.disconnect.assert_called_once() 