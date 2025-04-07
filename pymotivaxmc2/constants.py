DISCOVER_REQ_PORT = 7000
DISCOVER_RESP_PORT = 7001

NOTIFY_EVENTS = {
    'power', 'zone2_power', 'source', 'mode', 'volume', 'audio_input',
    'audio_bitstream', 'video_input', 'video_format',
    *[f'input_{i}' for i in range(1, 9)]
}
