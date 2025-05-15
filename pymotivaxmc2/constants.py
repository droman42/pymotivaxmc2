"""
Constants for the Emotiva integration.

This module defines constants used throughout the Emotiva integration.
"""

# Network ports
DISCOVER_REQ_PORT = 7000
DISCOVER_RESP_PORT = 7001
NOTIFY_PORT = 7001

# Protocol versions
PROTOCOL_VERSION = "1.0"

# Keepalive settings
DEFAULT_KEEPALIVE_INTERVAL = 30  # seconds

# Events to subscribe to
NOTIFY_EVENTS = [
    "power",
    "volume",
    "input",
    "mute",
    "mode",
    "menu",
    "bar",
    "zone2_power",
    "zone2_volume",
    "zone2_input",
    "zone2_mute"
]

# Audio mode presets
MODE_PRESETS = [
    "direct",
    "stereo",
    "movie",
    "music",
    "game",
    "night",
    "reference"
]

# Input sources
INPUT_SOURCES = [
    "hdmi1",
    "hdmi2",
    "hdmi3",
    "hdmi4",
    "hdmi5",
    "hdmi6",
    "hdmi7",
    "coax1",
    "coax2",
    "optical1",
    "optical2",
    "analog1",
    "analog2",
    "analog3",
    "phono",
    "bluetooth",
    "usb",
    "network"
]

# Menu commands
MENU_COMMANDS = [
    "up",
    "down",
    "left",
    "right",
    "select",
    "back",
    "home"
]

# Bar notification types
BAR_TYPES = [
    "off",
    "bar",
    "text",
    "subtext"
]

# Request types
REQUEST_TYPES = [
    "discover",
    "notifyRequest",
    "propertyRequest",
    "control"
]

# Response types
RESPONSE_TYPES = [
    "transponder",
    "command",
    "notify",
    "error"
]

# State properties
STATE_PROPERTIES = [
    "power",
    "volume",
    "mute",
    "input",
    "mode",
    "menu_active",
    "zone2_power",
    "zone2_volume",
    "zone2_mute",
    "zone2_input"
]

# Device info properties
DEVICE_INFO_PROPERTIES = [
    "model",
    "serial",
    "firmware",
    "mac",
    "protocol"
]

# Timeout settings
DEFAULT_COMMAND_TIMEOUT = 2.0  # seconds
DEFAULT_DISCOVERY_TIMEOUT = 5.0  # seconds
DEFAULT_RETRY_DELAY = 1.0  # seconds
MAX_RETRIES = 3
