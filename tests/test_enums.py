"""Test cases for pymotivaxmc2.enums module."""

import pytest
from enum import StrEnum
from pymotivaxmc2.enums import Command, Property, Input, Zone, MenuKey


class TestCommand:
    """Test cases for Command enum."""

    def test_inheritance(self):
        """Test that Command inherits from StrEnum."""
        assert issubclass(Command, StrEnum)

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for cmd in Command:
            assert isinstance(cmd.value, str)
            assert isinstance(cmd, str)  # StrEnum behavior

    def test_specific_commands_exist(self):
        """Test that specific important commands exist."""
        expected_commands = [
            "power_on",
            "power_off", 
            "mute",
            "mute_on",
            "mute_off",
            "set_volume",
            "volume",
            "hdmi1",
            "hdmi2",
            "coax1",
            "optical1",
            "zone2_power_on",
            "zone2_power_off",
            "zone2_volume"
        ]
        
        command_values = [cmd.value for cmd in Command]
        for expected in expected_commands:
            assert expected in command_values

    def test_command_enum_access(self):
        """Test accessing commands by name."""
        assert Command.POWER_ON == "power_on"
        assert Command.POWER_OFF == "power_off"
        assert Command.MUTE == "mute"
        assert Command.SET_VOLUME == "set_volume"

    def test_command_string_equality(self):
        """Test that command enums equal their string values."""
        assert Command.POWER_ON == "power_on"
        assert str(Command.POWER_ON) == "power_on"

    def test_zone2_commands_exist(self):
        """Test that Zone 2 specific commands exist."""
        zone2_commands = [cmd for cmd in Command if cmd.value.startswith("zone2_")]
        assert len(zone2_commands) > 0
        assert Command.ZONE2_POWER_ON in zone2_commands
        assert Command.ZONE2_POWER_OFF in zone2_commands

    def test_hdmi_commands_exist(self):
        """Test that HDMI input commands exist."""
        hdmi_commands = [cmd for cmd in Command if "hdmi" in cmd.value.lower()]
        assert len(hdmi_commands) >= 8  # Should have at least HDMI1-8
        assert Command.HDMI1 in hdmi_commands
        assert Command.HDMI8 in hdmi_commands


class TestProperty:
    """Test cases for Property enum."""

    def test_inheritance(self):
        """Test that Property inherits from StrEnum."""
        assert issubclass(Property, StrEnum)

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for prop in Property:
            assert isinstance(prop.value, str)
            assert isinstance(prop, str)  # StrEnum behavior

    def test_specific_properties_exist(self):
        """Test that specific important properties exist."""
        expected_properties = [
            "power",
            "volume",
            "loudness",
            "source",
            "mode",
            "keepAlive",
            "zone2_power",
            "zone2_volume"
        ]
        
        property_values = [prop.value for prop in Property]
        for expected in expected_properties:
            assert expected in property_values

    def test_property_enum_access(self):
        """Test accessing properties by name."""
        assert Property.POWER == "power"
        assert Property.VOLUME == "volume"
        assert Property.KEEPALIVE == "keepAlive"

    def test_version_properties_exist(self):
        """Test that version-related properties exist."""
        version_props = [prop for prop in Property if prop.value.startswith(("_", "Version"))]
        assert len(version_props) > 0
        assert Property.VERSION in version_props

    def test_mode_properties_exist(self):
        """Test that mode-related properties exist."""
        mode_props = [prop for prop in Property if "mode" in prop.value.lower()]
        assert len(mode_props) > 0
        assert Property.MODE in mode_props


class TestInput:
    """Test cases for Input enum."""

    def test_inheritance(self):
        """Test that Input inherits from StrEnum."""
        assert issubclass(Input, StrEnum)

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for inp in Input:
            assert isinstance(inp.value, str)
            assert isinstance(inp, str)  # StrEnum behavior

    def test_hdmi_inputs_exist(self):
        """Test that HDMI inputs exist."""
        hdmi_inputs = [inp for inp in Input if inp.value.startswith("hdmi")]
        assert len(hdmi_inputs) >= 8  # Should have at least HDMI1-8
        assert Input.HDMI1 in hdmi_inputs
        assert Input.HDMI8 in hdmi_inputs

    def test_coax_inputs_exist(self):
        """Test that coaxial inputs exist."""
        coax_inputs = [inp for inp in Input if inp.value.startswith("coax")]
        assert len(coax_inputs) >= 4  # Should have at least COAX1-4
        assert Input.COAX1 in coax_inputs
        assert Input.COAX4 in coax_inputs

    def test_optical_inputs_exist(self):
        """Test that optical inputs exist."""
        optical_inputs = [inp for inp in Input if inp.value.startswith("optical")]
        assert len(optical_inputs) >= 4  # Should have at least OPTICAL1-4
        assert Input.OPTICAL1 in optical_inputs
        assert Input.OPTICAL4 in optical_inputs

    def test_tuner_input_exists(self):
        """Test that tuner input exists."""
        assert Input.TUNER == "tuner"

    def test_input_enum_access(self):
        """Test accessing inputs by name."""
        assert Input.HDMI1 == "hdmi1"
        assert Input.COAX1 == "coax1"
        assert Input.OPTICAL1 == "optical1"
        assert Input.TUNER == "tuner"


class TestZone:
    """Test cases for Zone enum."""

    def test_inheritance(self):
        """Test that Zone inherits from StrEnum."""
        assert issubclass(Zone, StrEnum)

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for zone in Zone:
            assert isinstance(zone.value, str)
            assert isinstance(zone, str)  # StrEnum behavior

    def test_zones_exist(self):
        """Test that expected zones exist."""
        assert Zone.MAIN == "main"
        assert Zone.ZONE2 == "zone2"

    def test_zone_count(self):
        """Test that we have the expected number of zones."""
        zones = list(Zone)
        assert len(zones) == 2  # MAIN and ZONE2

    def test_zone_enum_access(self):
        """Test accessing zones by name."""
        assert Zone.MAIN == "main"
        assert Zone.ZONE2 == "zone2"


class TestMenuKey:
    """Test cases for MenuKey enum."""

    def test_inheritance(self):
        """Test that MenuKey inherits from StrEnum."""
        assert issubclass(MenuKey, StrEnum)

    def test_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        for key in MenuKey:
            assert isinstance(key.value, str)
            assert isinstance(key, str)  # StrEnum behavior

    def test_navigation_keys_exist(self):
        """Test that navigation keys exist."""
        expected_keys = ["up", "down", "left", "right", "enter", "back"]
        menu_key_values = [key.value for key in MenuKey]
        
        for expected in expected_keys:
            assert expected in menu_key_values

    def test_menu_key_enum_access(self):
        """Test accessing menu keys by name."""
        assert MenuKey.UP == "up"
        assert MenuKey.DOWN == "down"
        assert MenuKey.LEFT == "left"
        assert MenuKey.RIGHT == "right"
        assert MenuKey.ENTER == "enter"
        assert MenuKey.BACK == "back"

    def test_menu_key_count(self):
        """Test that we have the expected number of menu keys."""
        keys = list(MenuKey)
        assert len(keys) == 6  # UP, DOWN, LEFT, RIGHT, ENTER, BACK


class TestEnumConsistency:
    """Test cases for enum consistency and relationships."""

    def test_all_enums_are_str_enums(self):
        """Test that all enums inherit from StrEnum."""
        enums = [Command, Property, Input, Zone, MenuKey]
        for enum_class in enums:
            assert issubclass(enum_class, StrEnum)

    def test_no_duplicate_values_within_enums(self):
        """Test that there are no duplicate values within each enum."""
        enums = [Command, Property, Input, Zone, MenuKey]
        
        for enum_class in enums:
            values = [item.value for item in enum_class]
            assert len(values) == len(set(values)), f"Duplicate values found in {enum_class.__name__}"

    def test_enum_values_not_empty(self):
        """Test that no enum values are empty strings."""
        enums = [Command, Property, Input, Zone, MenuKey]
        
        for enum_class in enums:
            for item in enum_class:
                assert item.value != "", f"Empty value found in {enum_class.__name__}: {item.name}"
                assert item.value is not None, f"None value found in {enum_class.__name__}: {item.name}"

    def test_command_property_relationship(self):
        """Test relationships between Command and Property enums."""
        # Commands that should have corresponding properties
        command_property_pairs = [
            (Command.POWER_ON, Property.POWER),
            (Command.POWER_OFF, Property.POWER),
            (Command.LOUDNESS, Property.LOUDNESS),
            (Command.VOLUME, Property.VOLUME),
        ]
        
        for cmd, prop in command_property_pairs:
            assert cmd in Command
            assert prop in Property

    def test_zone_command_consistency(self):
        """Test that zone-related commands are consistent."""
        # Zone 1 (main) commands should have Zone 2 equivalents
        main_commands = ["power_on", "power_off", "volume", "mute"]
        
        for main_cmd in main_commands:
            zone2_cmd = f"zone2_{main_cmd}"
            command_values = [cmd.value for cmd in Command]
            
            # Check if zone2 equivalent exists
            if zone2_cmd in command_values:
                assert main_cmd in command_values
                assert zone2_cmd in command_values 