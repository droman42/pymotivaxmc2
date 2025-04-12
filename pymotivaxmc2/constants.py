"""
Constants for the eMotiva integration.

This module contains shared constants used throughout the package
to ensure consistency and improve code maintainability.
"""

# Network constants
DISCOVER_REQ_PORT = 7000
DISCOVER_RESP_PORT = 7001
DEFAULT_TIMEOUT = 2
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0

# Protocol version
PROTOCOL_VERSION = "3.1"

# Keepalive settings
DEFAULT_KEEPALIVE_INTERVAL = 10000  # 10 seconds
MAX_MISSED_KEEPALIVES = 3

# Commands
QUERY_INPUT_NAMES = "query_input_names"

# Notification events
NOTIFY_EVENTS = {
    'power',
    'source',
    'dim',
    'mode',
    'speaker_preset',
    'center',
    'subwoofer',
    'surround',
    'back',
    'volume',
    'loudness',
    'treble',
    'bass',
    'zone2_power',
    'zone2_volume',
    'zone2_input',
    'tuner_band',
    'tuner_channel',
    'tuner_signal',
    'tuner_program',
    'tuner_RDS',
    'audio_input',
    'audio_bitstream',
    'audio_bits',
    'video_input',
    'video_format',
    'video_space',
    'input_1',
    'input_2',
    'input_3',
    'input_4',
    'input_5',
    'input_6',
    'input_7',
    'input_8',
    'selected_mode',
    'selected_movie_music',
    'mode_ref_stereo',
    'mode_stereo',
    'mode_music',
    'mode_movie',
    'mode_direct',
    'mode_dolby',
    'mode_dts',
    'mode_all_stereo',
    'mode_auto',
    'mode_surround',
    'menu',
    'menu_update',
    'keepalive',
    'goodbye',
    'bar_update'
}

# Mode presets
MODE_PRESETS = {
    'stereo': 'Stereo',
    'direct': 'Direct',
    'dolby': 'Dolby',
    'dts': 'DTS',
    'all_stereo': 'All Stereo',
    'auto': 'Auto',
    'reference_stereo': 'Reference Stereo',
    'surround': 'Surround',
    'music': 'Music',
    'movie': 'Movie'
}

# Input sources
INPUT_SOURCES = {
    'tuner': 'Tuner',
    'hdmi1': 'HDMI 1',
    'hdmi2': 'HDMI 2',
    'hdmi3': 'HDMI 3',
    'hdmi4': 'HDMI 4',
    'hdmi5': 'HDMI 5',
    'hdmi6': 'HDMI 6',
    'hdmi7': 'HDMI 7',
    'hdmi8': 'HDMI 8',
    'coax1': 'Coax 1',
    'coax2': 'Coax 2',
    'coax3': 'Coax 3',
    'coax4': 'Coax 4',
    'optical1': 'Optical 1',
    'optical2': 'Optical 2',
    'optical3': 'Optical 3',
    'optical4': 'Optical 4',
    'analog1': 'Analog 1',
    'analog2': 'Analog 2',
    'analog3': 'Analog 3',
    'analog4': 'Analog 4',
    'analog5': 'Analog 5',
    'analog7.1': 'Analog 7.1',
    'front_in': 'Front In',
    'ARC': 'ARC',
    'usb_stream': 'USB Stream'
}
