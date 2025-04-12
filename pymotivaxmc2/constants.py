"""
Constants for the eMotiva integration.

This module contains shared constants used throughout the package
to ensure consistency and improve code maintainability.
"""

# Network ports
DISCOVER_REQ_PORT = 7000  # Port for discovery requests
DISCOVER_RESP_PORT = 7001  # Port for discovery responses
CONTROL_PORT = 7002  # Port for command control
NOTIFY_PORT = 7003  # Port for notifications
INFO_PORT = 7004  # Port for information requests
MENU_NOTIFY_PORT = 7005  # Port for menu notifications
SETUP_PORT_TCP = 7100  # TCP port for setup

# Protocol version
PROTOCOL_VERSION = "3.0"  # Protocol version for communication

# Keepalive settings
DEFAULT_KEEPALIVE_INTERVAL = 7500  # Default keepalive interval in milliseconds
MAX_MISSED_KEEPALIVES = 3  # Maximum number of missed keepalives before considering device offline

# Audio processing modes
MODE_PRESETS = {
    "stereo": "Stereo",
    "direct": "Direct",
    "dolby": "Dolby",
    "dts": "DTS",
    "movie": "Movie",
    "music": "Music",
    "all_stereo": "All Stereo",
    "auto": "Auto",
    "reference_stereo": "Reference Stereo",
    "surround_mode": "Surround"
}

# Input sources
INPUT_SOURCES = {
    "tuner": "Tuner",
    "hdmi1": "HDMI 1",
    "hdmi2": "HDMI 2",
    "hdmi3": "HDMI 3",
    "hdmi4": "HDMI 4",
    "hdmi5": "HDMI 5",
    "hdmi6": "HDMI 6",
    "hdmi7": "HDMI 7",
    "hdmi8": "HDMI 8",
    "coax1": "Coax 1",
    "coax2": "Coax 2",
    "coax3": "Coax 3",
    "coax4": "Coax 4",
    "optical1": "Optical 1",
    "optical2": "Optical 2",
    "optical3": "Optical 3",
    "optical4": "Optical 4",
    "analog1": "Analog 1",
    "analog2": "Analog 2",
    "analog3": "Analog 3",
    "analog4": "Analog 4",
    "analog5": "Analog 5",
    "analog7.1": "Analog 7.1",
    "front_in": "Front In",
    "ARC": "ARC",
    "usb_stream": "USB Stream",
    "zone2_analog1": "Zone 2 Analog 1",
    "zone2_analog2": "Zone 2 Analog 2",
    "zone2_analog3": "Zone 2 Analog 3",
    "zone2_analog4": "Zone 2 Analog 4",
    "zone2_analog5": "Zone 2 Analog 5",
    "zone2_analog71": "Zone 2 Analog 7.1",
    "zone2_analog8": "Zone 2 Analog 8",
    "zone2_front_in": "Zone 2 Front In",
    "zone2_ARC": "Zone 2 ARC",
    "zone2_ethernet": "Zone 2 Ethernet",
    "zone2_follow_main": "Zone 2 Follow Main",
    "zone2_coax1": "Zone 2 Coax 1",
    "zone2_coax2": "Zone 2 Coax 2",
    "zone2_coax3": "Zone 2 Coax 3",
    "zone2_coax4": "Zone 2 Coax 4",
    "zone2_optical1": "Zone 2 Optical 1",
    "zone2_optical2": "Zone 2 Optical 2",
    "zone2_optical3": "Zone 2 Optical 3",
    "zone2_optical4": "Zone 2 Optical 4"
}

# Notification events
NOTIFY_EVENTS = {
    "power",
    "volume",
    "mute",
    "input",
    "mode",
    "keepalive",
    "goodbye",
    "selected_mode",
    "selected_movie_music",
    "mode_ref_stereo",
    "mode_stereo",
    "mode_music",
    "mode_movie",
    "mode_direct",
    "mode_dolby",
    "mode_dts",
    "mode_all_stereo",
    "mode_auto",
    "mode_surround",
    "menu",
    "menu_update",
    "bar_update",
    "tuner_band",
    "tuner_channel",
    "tuner_signal",
    "tuner_program",
    "tuner_RDS",
    "audio_input",
    "audio_bitstream",
    "audio_bits",
    "video_input",
    "video_format",
    "video_space",
    "input_1",
    "input_2",
    "input_3",
    "input_4",
    "input_5",
    "input_6",
    "input_7",
    "input_8",
    "zone2_power",
    "zone2_volume",
    "zone2_input",
    "zone2_mute",
    "speaker_preset",
    "center",
    "subwoofer",
    "surround",
    "back",
    "width",
    "height",
    "loudness",
    "treble",
    "bass",
    "dim"
}
